import numpy as np
from scipy.io import loadmat
import pandas as pd
import mido

accrange = 0.05  # the range of a reference onset [s]


def label_create(txt_file, dataset, t, fs, length):
    if dataset == 'MAPS':
        df = pd.read_table(txt_file)
        iv_label = df.values.astype(float)
        iv_label = np.append(iv_label, np.ones((1, np.shape(iv_label)[0])).T, axis=1)
    elif dataset == 'MusicNet':
        df = pd.read_csv(txt_file)
        iv_label = df.values[:, [0, 1, 3, 2]].astype(float)
        iv_label[:, :2] /= fs
    elif dataset == 'Bach10':
        dic = loadmat(txt_file, simplify_cells=True)
        note_dic = dic['GTNotes']
        iv_label = np.empty((0, 4))
        for x in range(len(note_dic)):
            for y in range(len(note_dic[x])):
                iv_label = np.append(iv_label, np.array([[note_dic[x][y][0][0], note_dic[x][y][0][-1],
                                                          round(note_dic[x][y][1][0]), x]]), axis=0)
        iv_label[:, :2] *= 0.01
        iv_label = iv_label[np.argsort(iv_label[:, 0])]
    elif dataset == 'TRIOS':
        iv_label = np.load(txt_file)
    elif dataset == 'RWC':
        mid = mido.MidiFile(txt_file)
        mididict = []
        onset = np.empty((0, 3))
        offset = np.empty((0, 3))
        for x in mid:
            mididict.append(x.dict())
        mem = 0
        for y in mididict:
            settime = y['time'] + mem
            y['time'] = settime
            mem = y['time']
            if y['type'] == 'note_on' and y['velocity'] == 0:
                y['type'] = 'note_off'
            if y['type'] == 'note_on':
                onset = np.append(onset, np.array([[y['time'], y['note'], y['channel']]]), axis=0)
            elif y['type'] == 'note_off':
                offset = np.append(offset, np.array([[y['time'], y['note'], y['channel']]]), axis=0)
        iv_label = np.zeros((np.shape(onset)[0], 4))
        d = np.zeros(np.shape(onset)[0])
        for i in range(np.shape(onset)[0]):
            matchvec = np.where(np.all(offset[:, 1:] == onset[i, 1:], 1))[0]
            imatch = matchvec[d[matchvec] == 0][0]
            iv_label[i] = [onset[i, 0], offset[imatch, 0], onset[i, 1], onset[i, 2]]
            d[imatch] = 1
    else:
        raise Exception('Select the appropriate value for dataset')
    if length > 0:
        iv_label = iv_label[iv_label[:, 0] < length]
    instnum = np.unique(iv_label[:, 3])
    pr_label = np.zeros((len(t), 128, len(instnum)), dtype=np.int64)
    for k in range(len(instnum)):
        iv_label_inst = iv_label[iv_label[:, 3] == instnum[k]]
        p_label = np.asarray(iv_label_inst[:, 2], dtype=int)
        for i in range(len(t)):
            pr_label[i, p_label[(iv_label_inst[:, 0] <= t[i]) & (t[i] <= iv_label_inst[:, 1])], k] = 1
    return pr_label, iv_label


def framelevel_evaluate(pr, pr_label):
    feval = np.zeros(3, dtype=np.int64)
    if pr.ndim == 3:
        pr_sum = np.sum(pr, 2)
        pr_sum[pr_sum > 1] = 1
    else:
        pr_sum = pr
    # pr_label_sum = np.sum(pr_label, 0)
    pr_label_sum = np.sum(pr_label, 2)
    pr_label_sum[pr_label_sum > 1] = 1
    feval[0] = np.sum(pr_sum * pr_label_sum)  # TP
    feval[1] = np.sum(pr_sum) - feval[0]  # FP
    feval[2] = np.sum(pr_label_sum) - feval[0]  # FN
    return feval


def notelevel_evaluate(iv, iv_label, accrange=accrange):
    neval = np.zeros(3, dtype=np.int64)
    for i in range(0, 128):
        tref = iv_label[:, 0][iv_label[:, 2] == i]
        test = iv[:, 0][iv[:, 2] == i]
        for j in range(len(tref)):
            if any(np.abs(tref[j] - test) <= accrange):
                neval[0] += 1  # TP
    neval[1] = len(iv[:, 0]) - neval[0]  # FP
    neval[2] = len(iv_label[:, 0]) - neval[0]  # FN
    return neval


def framelevel_evaluate_instwise_tpfn(pr, pr_label):
    feval_instwise = np.zeros((np.shape(pr_label)[2], 2), dtype=np.int64)
    for k in range(np.shape(pr_label)[2]):
        feval_instwise[k][0] = np.sum(pr * pr_label[:, :, k])  # TP
        feval_instwise[k][1] = np.sum(pr_label[:, :, k]) - feval_instwise[k][0]  # FN
    return feval_instwise
