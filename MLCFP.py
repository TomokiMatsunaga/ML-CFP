from tkinter import filedialog
from tkinter import *
import os
import argparse
import numpy as np
from scipy import signal
from scipy.io import wavfile
import torch
import copy
from operator import itemgetter
import glob
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
from evaluation import label_create, framelevel_evaluate, framelevel_evaluate_instwise_tpfn
import time

# Parameter setting
dataset = 'MAPS'  # 'MAPS', 'MusicNet', 'Bach10', 'TRIOS', 'RWC'
evaluation_on = 1  # 0 : off   1 : on
instrument_wise = 0  # 0 : Collective   1 : Collective & Respective
short = 0  # 0 : Full   T : T [s]

window = 'blackmanharris'  # window function
W = 0.24  # window size [s]
H = 0.02  # hop size [s]
fftnum = 4  # segment length (fftnum * W [s])
p0 = 2e-5  # reference sound pressure [Pa]

qc = 4000  # cutoff quefrency [Hz]
# tATH = 100  # [ms]
# cpsth = 0.2  # [dB]
qp = [10, 50, 110]  # cutoff quefrencies for multi-layer features [Hz]
peakth = [12, 11, 11, 9]  # peak thresholds
peakd = 2  # peak distance [Hz]

alpha = [8, 8, 6, 4]  # scaling factors
fu1 = [0, 0, 0, 600]  # lower cutoff frequencies [Hz]
fu2 = [3000, 4500, 6500, 18000]  # upper cutoff frequencies [Hz]
sigma = 0.2  # proportion used in Peak-Picking

start = 21  # lower annotated pitch threshold
end = 108  # upper annotated pitch threshold
plow = [27, 39]  # low pitch thresholds
splth = 30  # SPL threshold [dB]
sigmam = 1.2  # proportion used in Missing Fundamental Detection
hm = 4  # harmonic order used in Missing Fundamental Detection (hm + 1)

deltanb = 2  # neighborhood interval
lsnb = -17  # lower SPL differences [dB]
usnb = 3  # upper SPL differences [dB]
pref = [50, 63, 76]  # reference pitch thresholds
hcd = 2  # harmonic order used in candidate pitch removal step (hcd + 1)
hhn = 2  # harmonic order used to remove harmonic pitches (hhn + 1)
hnb = 2  # harmonic order used to remove neighborhood pitches (hnb + 1)
intth = 35  # interval threshold
deltash = [-2, 4]  # neighborhood pitch differences
sigmash = 1  # proportion used to remove subharmonic pitches

rt = 0.3  # time interval threshold [s]
rd = 0.1  # duration threshold [s]
sigmat = 0.6  # ratio of activated positions

###

os.makedirs('temp', exist_ok=True)


def dataset_type(dataset):
    if dataset == 'MAPS':
        ref_type = '.txt'
    elif dataset == 'MusicNet':
        ref_type = '.csv'
    elif dataset == 'Bach10':
        ref_type = '.mat'
    elif dataset == 'TRIOS':
        ref_type = '.npy'
    elif dataset == 'RWC':
        ref_type = '.mid'
    else:
        raise Exception('The specified dataset is not registered')
    return ref_type


def file_import(wav_file):
    fs, data = wavfile.read(wav_file)
    if data.ndim == 1:
        data = data / np.max(np.abs(data))
    else:
        data = np.sum(data, 1)
        data = data / np.max(np.abs(data))
    return fs, data


def peak_select(spc, height, distance):
    spcpeaks = np.where(spc >= height)[0]
    if len(spcpeaks) > 0:
        dpeak = np.where(np.diff(spcpeaks, 1) > distance)[0] + 1
        dpeak = np.concatenate([np.array([0]), dpeak, np.array([len(spcpeaks)])])
        select_peaks = np.zeros(len(dpeak) - 1, dtype=np.int64)
        for i in range(len(dpeak) - 1):
            peakset = spcpeaks[dpeak[i]:dpeak[i + 1]]
            select_peaks[i] = peakset[np.argmax(spc[peakset])]
    else:
        select_peaks = np.array([], dtype=np.int64)
    return select_peaks


def spcpeak_extraction(spc, fs, snum, tscale, qc=qc, qp=qp, peakth=peakth, peakd=peakd):
    cps = np.fft.ifft(spc)
    barU = np.zeros((len(qp) + 1, len(cps)))
    # hicut = len(tscale[tscale < tATH / 1000])
    for i in range(len(qp) + 1):
        V = copy.deepcopy(cps)
        V[np.abs(tscale) < 1 / qc] = 0
        # AmpV = np.abs(V)
        # V[hicut + 1:-hicut][AmpV[hicut + 1:-hicut] > cpsth] = cpsth
        if i > 0:
            V[np.abs(tscale) > 1 / qp[i - 1]] = 0
        CoS = np.fft.fft(V, snum)
        CoS = np.real(CoS)
        peak = peak_select(CoS, peakth[i], peakd // (fs / snum))
        if i == 0:
            barU0 = np.zeros_like(spc)
            barU0[peak] = spc[peak]
        barU[i][peak] = CoS[peak]
    return barU0, barU


def cpspeak_extraction(barU, f, snum, peakth=peakth, alpha=alpha, fu1=fu1, fu2=fu2, sigma=sigma):
    barV = np.zeros_like(barU)
    for i in range(len(alpha)):
        Delta = copy.deepcopy(barU[i])
        Delta[np.abs(f) < fu1[i]] = 0
        Delta[np.abs(f) > fu2[i]] = 0
        CoD = np.fft.ifft(Delta)
        barV[i] = snum * np.real(CoD) / (2 * alpha[i] + 1)
        if i < len(alpha) - 1:
            barV[i][barV[i] < peakth[i]] = 0
        else:
            barV[i][barV[i] < max(peakth[i], np.max(barV[i]) * sigma)] = 0
    return barV


def note_assignment(pf, pq, barU0, barU, barV, snum, alpha=alpha):
    Ztensor = torch.zeros(torch.max(pf) + 1, dtype=torch.float64)
    u0 = torch.from_numpy(barU0[1:(1 + snum) // 2]).clone()
    u0 = u0.to(torch.float64)
    Ztensor.scatter_reduce_(0, pf[0], u0, reduce='amax', include_self=False)
    Z0 = Ztensor.numpy()[:-1]
    Zftensor = torch.zeros(len(alpha), torch.max(pf) + 1, dtype=torch.float64)
    u = torch.from_numpy(barU[:, 1:(1 + snum) // 2]).clone()
    u = u.to(torch.float64)
    Zftensor.scatter_reduce_(1, pf, u, reduce='amax', include_self=False)
    Zf = Zftensor.numpy()[:, :-1]
    Zqtensor = torch.zeros(len(alpha), torch.max(pq) + 1, dtype=torch.float64)
    v = torch.from_numpy(barV[:, 1:(1 + snum) // 2]).clone()
    v = v.to(torch.float64)
    Zqtensor.scatter_reduce_(1, pq, v, reduce='amax', include_self=False)
    Zq = Zqtensor.numpy()[:, :-1]
    return Z0, Zf, Zq


Nnum = np.array(range(0, 128))
I = np.array([12, 19, 24, 28, 31, 34, 36, 38, 40, 42, 43, 44, 46])
I = np.append(I, np.arange(47, 128))
I0 = np.append(0, I)


def lowpitch_addition(Z0, Zf, Zq, addIvec, I0vec, start=start, plow=plow, splth=splth, sigmam=sigmam):
    upitch = Nnum[Z0 >= splth]
    for i in range(len(upitch)):
        if (upitch[i] - I[1] > plow[0]) & (upitch[i] - I[0] > plow[1]):
            break
        if start <= upitch[i] - I[1] <= plow[0]:
            upitch1 = upitch[i] - I[1]
            if set(upitch1 + addIvec[1:]) <= set(upitch):
                hmpeaks1 = max(0, np.max(itemgetter(upitch1 + I[0] + np.arange(0, 2))(Zq[0])) - np.max(
                    itemgetter(upitch1 + I[4] + np.arange(0, 2))(Zq[0]))) + max(0, np.max(
                    itemgetter(upitch1 + I[1] + np.arange(0, 2))(Zq[0])) - np.max(
                    itemgetter(upitch1 + I[4] + np.arange(0, 2))(Zq[0])))
                if max(0, np.max(itemgetter(upitch1 + np.arange(0, 2))(Zq[0])) - np.max(
                        itemgetter(upitch1 + I[4] + np.arange(0, 2))(Zq[0]))) >= hmpeaks1 * sigmam:
                    Zf[0][upitch1 + I[0]] = np.max(itemgetter(upitch1 + I0vec)(Zf[0]))
                    Zf[0][upitch1] = np.max(itemgetter(upitch1 + I0vec)(Zf[0]))
                    Z0[upitch1 + I[0]] = np.max(itemgetter(upitch1 + I0vec)(Z0))
                    Z0[upitch1] = np.max(itemgetter(upitch1 + I0vec)(Z0))
        if plow[0] < upitch[i] - I[0] <= plow[1]:
            upitch0 = upitch[i] - I[0]
            if set(upitch0 + addIvec) <= set(upitch):
                hmpeaks0 = max(0, np.max(itemgetter(upitch0 + I[0] + np.arange(0, 2))(Zq[0])) - np.max(
                    itemgetter(upitch0 + I[4] + np.arange(0, 2))(Zq[0]))) + max(0, np.max(
                    itemgetter(upitch0 + I[1] + np.arange(0, 2))(Zq[0])) - np.max(
                    itemgetter(upitch0 + I[4] + np.arange(0, 2))(Zq[0])))
                if max(0, np.max(itemgetter(upitch0 + np.arange(0, 2))(Zq[0])) - np.max(
                        itemgetter(upitch0 + I[4] + np.arange(0, 2))(Zq[0]))) >= hmpeaks0 * sigmam:
                    Zf[0][upitch0] = np.max(itemgetter(upitch0 + I0vec)(Zf[0]))
                    Z0[upitch0] = np.max(itemgetter(upitch0 + I0vec)(Z0))
    return Z0, Zf


infty = 1000


def pitch_select(Z0, Zf, Zq, cdIvec, nbIvec, peakth=peakth, start=start, end=end, splth=splth, deltanb=deltanb,
                 lsnb=lsnb, usnb=usnb, pref=pref, hhn=hhn, intth=intth, deltash=deltash, sigmash=sigmash):
    idx0 = np.where(Z0 >= splth)[0]
    idx0 = idx0[(start <= idx0) & (idx0 <= end)]
    upitch = Nnum[Z0 >= splth]

    cZ0 = copy.deepcopy(Z0)
    i = 0
    while i < len(idx0):
        # candidate pitch removal step
        hmidx = idx0[i] + cdIvec
        if all(hmidx <= 127):
            if all(itemgetter(hmidx)(Zf[0]) == 0):
                idx0 = np.delete(idx0, i)
                continue

        # neighborhood pitch removal step
        c = False
        while True:
            j = 0
            while True:
                d0 = idx0 - idx0[i + j]
                nbidu = np.where((0 <= d0) & (d0 <= deltanb))[0]
                nbMidu = itemgetter(idx0[nbidu])(cZ0)
                if np.argmin(nbMidu) == 0:
                    break
                elif np.min(nbMidu) == infty:
                    break
                else:
                    j += np.argmin(nbMidu)
            if cZ0[idx0[i + j]] == infty:
                break
            cZ0[idx0[i + j]] = infty
            d = np.abs(idx0 - idx0[i + j])
            nbid = np.where((0 < d) & (d <= deltanb))[0]
            if len(nbid) > 0:
                if Z0[idx0[i + j]] < np.max(itemgetter(idx0[nbid])(Z0)) + lsnb:
                    idx0 = np.delete(idx0, i + j)
                    if j == 0:
                        c = True
                elif Z0[idx0[i + j]] < np.max(itemgetter(idx0[nbid])(Z0)) + usnb:
                    if not (set(idx0[i + j] + nbIvec) <= set(upitch)):
                        idx0 = np.delete(idx0, i + j)
                        if j == 0:
                            c = True
            if j == 0:
                break
        if c:
            continue

        # harmonic pitch removal step
        l = 0
        while idx0[i] + I[l] <= idx0[-1]:
            if set([idx0[i] + I[l]]) <= set(idx0):
                if idx0[i] + I[l] < pref[0]:
                    k = 0
                else:
                    k = np.where(idx0[i] + I[l] - np.array(pref) >= 0)[0][-1] + 1
                if np.max(itemgetter(idx0[i] + I[l] + np.arange(-1, 1))(Zf[k])) == 0:
                    idx0 = np.delete(idx0, np.where(idx0 == idx0[i] + I[l])[0])
                    l += 1
                    continue
                for j in range(hhn + 1):
                    if idx0[i] + I[l] - I0[j] == 127:
                        if Zq[k][idx0[i] + I[l] - I0[j]] == 0:
                            idx0 = np.delete(idx0, np.where(idx0 == idx0[i] + I[l])[0])
                            break
                    elif idx0[i] + I[l] - I0[j] >= 0:
                        if max(itemgetter(idx0[i] + I[l] - I0[j] + np.arange(0, 2))(Zq[k])) == 0:
                            idx0 = np.delete(idx0, np.where(idx0 == idx0[i] + I[l])[0])
                            break
            l += 1

        # neighborhood harmonic pitch removal step
        j = 0
        while j < len(idx0) - (i + 1):
            if all(I - (idx0[i + 1 + j] - idx0[i]) != 0):
                d = np.abs(I - (idx0[i + 1 + j] - idx0[i]))
                nbIid = np.where((0 < d) & (d <= deltanb))[0]
                if len(nbIid) > 0:
                    nbidx0 = idx0[i] + I[nbIid]
                    nbidx0 = nbidx0[nbidx0 <= 127]
                    if len(nbidx0) > 0:
                        if Z0[idx0[i + 1 + j]] < np.max(itemgetter(nbidx0)(Z0)) + lsnb:
                            idx0 = np.delete(idx0, i + 1 + j)
                            continue
                        elif Z0[idx0[i + 1 + j]] < np.max(
                                itemgetter(nbidx0)(Z0)) + usnb:
                            if not (set(idx0[i + 1 + j] + nbIvec) <= set(upitch)):
                                idx0 = np.delete(idx0, i + 1 + j)
                                continue
                if idx0[i + 1 + j] - idx0[i] >= intth:
                    if idx0[i + 1 + j] < pref[0]:
                        k = 0
                    else:
                        k = np.where(idx0[i + 1 + j] - np.array(pref) >= 0)[0][-1] + 1
                    for m in range(hhn + 1):
                        if idx0[i + 1 + j] - I0[m] == 127:
                            if Zq[k][idx0[i + 1 + j] - I0[m]] == 0:
                                idx0 = np.delete(idx0, i + 1 + j)
                                break
                        elif idx0[i + 1 + j] - I0[m] >= 0:
                            if max(itemgetter(idx0[i + 1 + j] - I0[m] + np.arange(0, 2))(Zq[k])) == 0:
                                idx0 = np.delete(idx0, i + 1 + j)
                                break
                    else:
                        j += 1
                    continue
            j += 1
        i += 1

    # neighborhood subharmonic pitch removal step
    for i in idx0:
        preidx0 = idx0[idx0 < i]
        c = True
        for l in preidx0:
            if any(i == l + I):
                c = False
                break
        if c:
            continue
        for m in range(deltash[0], deltash[1] + 1):
            commonidx0 = np.array(list(set(idx0) & set(i - m + I0)))
            commonidx0 = commonidx0[commonidx0 != i]
            if len(commonidx0) != 0:
                if i < pref[0]:
                    k = 0
                else:
                    k = np.where(i - np.array(pref) >= 0)[0][-1] + 1
                commonZq = Zq[k]
                Zqth = peakth[k]

                if m <= -2:
                    if (commonZq[i] <= commonZq[i + 1]) & (commonZq[i + 1] <= commonZq[i + 2]):
                        idx0 = np.delete(idx0, np.where(idx0 == i)[0])
                        break
                    continue
                if m == -1:
                    if commonZq[i] > commonZq[i + 1]:
                        continue
                    if commonZq[i + 1] <= commonZq[i + 2]:
                        idx0 = np.delete(idx0, np.where(idx0 == i)[0])
                        break
                    if all(commonidx0 == i + 1):
                        continue
                if m == 1:
                    if np.max(itemgetter(i + np.arange(0, 2))(commonZq)) <= commonZq[i - 1]:
                        if commonZq[i] >= commonZq[i + 1]:
                            idx0 = np.delete(idx0, np.where(idx0 == i)[0])
                            break
                    if all(commonidx0 == i - 1):
                        continue
                if m >= 2:
                    if np.max(itemgetter(i + np.arange(0, 2))(commonZq)) <= commonZq[i - 1]:
                        idx0 = np.delete(idx0, np.where(idx0 == i)[0])
                        break
                    continue
                for j in commonidx0:
                    if (j == i - 1) | (j == i + 1):
                        continue
                    hmnum = np.where(I0 == j - (i - m))[0][0]
                    if j == 127:
                        Zqth = np.append(Zqth, itemgetter(j - I0[:hmnum])(commonZq))
                        Zqth = np.append(Zqth, itemgetter(j - I0[1:hmnum] + 1)(commonZq))
                    else:
                        Zqth = np.append(Zqth, itemgetter(j - I0[:hmnum])(commonZq))
                        Zqth = np.append(Zqth, itemgetter(j - I0[:hmnum] + 1)(commonZq))
                if np.max(itemgetter(i + np.arange(0, 2))(commonZq)) < np.max(Zqth) * sigmash:
                    idx0 = np.delete(idx0, np.where(idx0 == i)[0])
                    break
    idx = idx0.tolist()
    return idx


eps = 1e-7
split = 10


def peaks_decision(fs, data, short=short, window=window, W=W, H=H, fftnum=fftnum, p0=p0, qc=qc, qp=qp, peakth=peakth,
                   peakd=peakd, alpha=alpha, fu1=fu1, fu2=fu2, sigma=sigma, start=start, end=end, plow=plow,
                   splth=splth, sigmam=sigmam, hm=hm, deltanb=deltanb, lsnb=lsnb, usnb=usnb, pref=pref, hhn=hhn,
                   intth=intth, deltash=deltash, sigmash=sigmash):
    snum1 = round(W * fs)
    snum = fftnum * snum1
    tscale = np.fft.fftfreq(snum, d=fs / snum)
    if short == 0:
        f, t, stft = signal.stft(data, fs, window, nperseg=snum1, noverlap=round((W - H) * fs), nfft=snum,
                                 return_onesided=False)
    else:
        f, t, stft = signal.stft(data[:round(short * fs)], fs, window, nperseg=snum1, noverlap=round((W - H) * fs),
                                 nfft=snum, return_onesided=False)
    U = 20 * np.log10(np.abs(stft) / p0 + eps)
    del stft
    val = np.where(np.max(U, 0) >= splth)[0]
    pr0 = np.zeros((len(t), 128), dtype=np.int64)
    pf = np.round(12 * np.log2(f[1:(1 + snum) // 2] / 440)) + 69
    pq = np.round(12 * np.log2(1 / (tscale[1:(1 + snum) // 2] * 440))) + 69
    pf_tensor = torch.from_numpy(np.tile(pf, (len(peakth), 1))).clone().to(torch.int64)
    pq_tensor = torch.from_numpy(np.tile(pq, (len(peakth), 1))).clone().to(torch.int64)
    pf_tensor[pf_tensor < 0] = 128
    pf_tensor[pf_tensor > 127] = 128
    pq_tensor[pq_tensor < 0] = 128
    pq_tensor[pq_tensor > 127] = 128
    addIvec = I[:hm]
    I0vec = I0[:hm + 1]
    cdIvec = I[:hcd]
    nbIvec = I[:hnb]
    for i in val:
        barU0, barU = spcpeak_extraction(U[:, i], fs, snum, tscale, qc, qp, peakth, peakd)
        barV = cpspeak_extraction(barU, f, snum, peakth, alpha, fu1, fu2, sigma)
        Z0, Zf, Zq = note_assignment(pf_tensor, pq_tensor, barU0, barU, barV, snum, alpha)
        Z0, Zf = lowpitch_addition(Z0, Zf, Zq, addIvec, I0vec, start, plow, splth, sigmam)
        idx = pitch_select(Z0, Zf, Zq, cdIvec, nbIvec, peakth, start, end, splth, deltanb, lsnb,
                           usnb, pref, hhn, intth, deltash, sigmash)
        for j in idx:
            pr0[i][j] = 1
    return t, pr0


def temporal_continuity(pr0, H=H, start=start, end=end, rt=rt, rd=rd, sigmat=sigmat):
    tdiss = round(rt / H)
    tlens = round(rd / H)
    pr = np.zeros_like(pr0)
    iv = np.empty((0, 3))
    for i in range(start, end + 1):
        tact = np.where(pr0[:, i] == 1)[0]
        if len(tact) == 0:
            continue
        j = 0
        while j < len(tact):
            k = j
            while k < len(tact):
                l = np.where(tact <= tact[k] + tdiss)[0][-1]
                if l == k:
                    break
                else:
                    k = l
            while k > j:
                if np.count_nonzero(pr0[tact[j]:tact[k] + 1, i] == 1) / (tact[k] - tact[j] + 1) < sigmat:
                    k -= 1
                else:
                    break
            if k > j:
                while True:
                    m = j
                    c = False
                    while m < k:
                        if np.count_nonzero(pr0[tact[m]:tact[k] + 1, i] == 1) / (tact[k] - tact[m] + 1) < sigmat:
                            m += 1
                        else:
                            c = True
                            break
                    if c:
                        if k == l:
                            break
                        else:
                            k += 1
                    else:
                        k -= 1
                        break
            if tact[k] - tact[j] >= tlens:
                pr[tact[j]:tact[k] + 1, i] = 1
                iv = np.append(iv, np.array([[tact[j], tact[k], i]]), axis=0)
                j = k + 1
            else:
                j += 1
    iv[:, :2] *= H
    iv = iv[np.argsort(iv[:, 0])]
    return pr, iv


def parallel_evaluation(wav_file, txt_path, ref_type, dataset, instrument_wise, instlist, short=short, window=window,
                        W=W, H=H, fftnum=fftnum, p0=p0, qc=qc, qp=qp, peakth=peakth, peakd=peakd, alpha=alpha, fu1=fu1,
                        fu2=fu2, sigma=sigma, start=start, end=end, plow=plow, splth=splth, sigmam=sigmam, hm=hm,
                        deltanb=deltanb, lsnb=lsnb, usnb=usnb, pref=pref, hhn=hhn, intth=intth, deltash=deltash,
                        sigmash=sigmash, rt=rt, rd=rd, sigmat=sigmat):
    fs, data = wavfile.read(wav_file)
    t, pr0 = peaks_decision(fs, data, short, window, W, H, fftnum, p0, qc, qp, peakth, peakd, alpha, fu1,
                            fu2, sigma, start, end, plow, splth, sigmam, hm, deltanb, lsnb,
                            usnb, pref, hhn, intth, deltash, sigmash)
    pr, iv0 = temporal_continuity(pr0, H, start, end, rt, rd, sigmat)
    np.savez_compressed('temp/comp/' + os.path.splitext(os.path.basename(wav_file))[0], pr=pr)

    txt_file = txt_path + os.path.splitext(os.path.basename(wav_file))[0] + ref_type
    pr_label, iv_label = label_create(txt_file, dataset, t, fs, short)
    np.savez_compressed('temp/label/' + os.path.splitext(os.path.basename(wav_file))[0], pr_label=pr_label)
    feval = framelevel_evaluate(pr, pr_label)
    P = feval[0] / (feval[0] + feval[1])
    R = feval[0] / (feval[0] + feval[2])
    F = 2 * feval[0] / (2 * feval[0] + feval[1] + feval[2])
    if P < 0.4 and R < 0.4 and F < 0.4:
        print(os.path.splitext(os.path.basename(wav_file))[0], 'TP:', feval[0], 'FP:', feval[1], 'FN:', feval[2])
    if instrument_wise == 1:
        feval_instwise0 = framelevel_evaluate_instwise_tpfn(pr, pr_label)
        feval_instwise = np.zeros((len(instlist), 2), dtype=np.int64)
        instnum = np.unique(iv_label[:, 3])
        for k in range(len(instnum)):
            i = np.where(instlist == instnum[k])[0]
            feval_instwise[i] = feval_instwise0[k]
        return feval, feval_instwise
    else:
        return feval


def extract_evaluation(filename, txt_path, dataset, instrument_wise, instlist, **kwargs):
    ref_type = dataset_type(dataset)
    fevalsum = np.zeros(3, dtype=np.int64)
    fevalsum_instwise = np.zeros((len(instlist), 2), dtype=np.int64)
    with ProcessPoolExecutor() as executor:
        futures = [executor.submit(parallel_evaluation, wav_file, txt_path, ref_type, dataset, instrument_wise,
                                   instlist, **kwargs) for wav_file in glob.glob(filename)]
    if instrument_wise == 0:
        for future in as_completed(futures):
            fevalsum += future.result()
        print('frame-level', 'TP:', fevalsum[0], 'FP:', fevalsum[1], 'FN:', fevalsum[2])
        print('F-measure:', 2 * fevalsum[0] / (2 * fevalsum[0] + fevalsum[1] + fevalsum[2]))
    elif instrument_wise == 1:
        for future in as_completed(futures):
            fevalsum += future.result()[0]
            fevalsum_instwise += future.result()[1]
        print('frame-level', 'TP:', fevalsum[0], 'FP:', fevalsum[1], 'FN:', fevalsum[2])
        print('F-measure:', 2 * fevalsum[0] / (2 * fevalsum[0] + fevalsum[1] + fevalsum[2]))
        for k in range(len(instlist)):
            print('frame-level (inst:' + str(instlist[k]) + ')', 'TP:', fevalsum_instwise[k][0], 'FN:',
                  fevalsum_instwise[k][1])
            print('Recall', fevalsum_instwise[k][0] / (fevalsum_instwise[k][0] + fevalsum_instwise[k][1]))


def extraction_detail_eval(filename, txt_path, csv_path):
    with open(csv_path, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['name', 'TP', 'FP', 'FN'])
    for npz_file in glob.glob(filename):
        kw = np.load(npz_file)
        txt_file = txt_path + os.path.basename(npz_file)
        txt_kw = np.load(txt_file)
        pr = kw['pr']
        pr_label = txt_kw['pr_label']
        feval = framelevel_evaluate(pr, pr_label)
        with open(csv_path, 'a') as f:
            writer = csv.writer(f)
            writer.writerow(np.append(os.path.splitext(os.path.basename(npz_file))[0], feval))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation_on', type=int)
    parser.add_argument('--dataset')
    parser.add_argument('--instrument_wise', type=int)
    parser.add_argument('--short', type=float)
    args = parser.parse_args()
    if args.evaluation_on is not None:
        if args.evaluation_on != 0 and args.evaluation_on != 1:
            raise Exception('Select 0 or 1 for evaluation_on')
        else:
            evaluation_on = args.evaluation_on
    if args.dataset is not None:
        dataset = args.daraset
    if args.instrument_wise is not None:
        if args.instrument_wise != 0 and args.instrument_wise != 1:
            raise Exception('Select 0 or 1 for instrument_wise')
        else:
            instrument_wise = args.instrument_wise
    if args.short is not None:
        short = args.short

    print('Please open .wav files')
    root = Tk()
    root.withdraw()
    wav_file = filedialog.askopenfilename(filetypes=[('.wav files', '*.wav')])
    print(wav_file)
    if evaluation_on == 1:
        ref_type = dataset_type(dataset)
        print('Please open ' + ref_type + ' files')
        txt_file = filedialog.askopenfilename(filetypes=[(ref_type + ' files', '*' + ref_type)])
        print(txt_file)
    fs, data = file_import(wav_file)
    time_start = time.perf_counter()
    t, pr0 = peaks_decision(fs, data, short)
    pr, iv0 = temporal_continuity(pr0)
    time_end = time.perf_counter()
    if evaluation_on == 0:
        np.savez_compressed('temp/pianoroll', prest=pr)
    elif evaluation_on == 1:
        pr_label, iv_label = label_create(txt_file, dataset, t, fs, short)
        np.savez_compressed('temp/pianoroll', prest=pr, prref=pr_label)
        feval = framelevel_evaluate(pr, pr_label)
        print('frame-level', 'TP:', feval[0], 'FP:', feval[1], 'FN:', feval[2])
        print('F-measure:', 2 * feval[0] / (2 * feval[0] + feval[1] + feval[2]))
        if instrument_wise == 1:
            feval_instwise = framelevel_evaluate_instwise_tpfn(pr, pr_label)
            instnum = np.unique(iv_label[:, 3])
            for k in range(len(instnum)):
                print('frame-level (inst:' + str(instnum[k]) + ')', 'TP:', feval_instwise[k][0], 'FN:',
                      feval_instwise[k][1])
                print('Recall', feval_instwise[k][0] / (feval_instwise[k][0] + feval_instwise[k][1]))
    print('RunTime:', time_end - time_start)
