import matplotlib.pyplot as plt
import numpy as np
import argparse

H = 0.02  # hop size [s]
evaluation_on = 1  # 0 : off   1 : on


def plt_pianoroll(pr, H=H):
    pact = np.where(pr == 1)
    tact = pact[0] * H

    fig = plt.figure()
    plt.scatter(tact, pact[1], color='k', s=5)
    plt.xlim(0, tact[-1])
    plt.ylim(21, 108)
    plt.xlabel('Time [sec]', fontsize=18)
    plt.ylabel('Piano roll', fontsize=18)
    plt.show()
    return fig


def plt_pianoroll_comparison(pr, pr_label, H=H):
    pestact = np.where(pr == 1)
    t_pestact = pestact[0] * H

    prefact = np.where(pr_label == 1)
    t_prefact = prefact[0] * H

    fig1 = plt.figure()
    plt.scatter(t_pestact, pestact[1], color='k', s=5)
    plt.xlim(0, max(t_pestact[-1], t_prefact[-1]))
    plt.ylim(21, 108)
    plt.xlabel('Time [sec]', fontsize=18)
    plt.ylabel('Piano roll', fontsize=18)
    plt.title('prediction', fontsize=18)
    plt.show()
    fig2 = plt.figure()
    plt.scatter(t_prefact, prefact[1], color='k', s=5)
    plt.xlim(0, max(t_pestact[-1], t_prefact[-1]))
    plt.ylim(21, 108)
    plt.xlabel('Time [sec]', fontsize=18)
    plt.ylabel('Piano roll', fontsize=18)
    plt.title('ground truth', fontsize=18)
    plt.show()
    return fig1, fig2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluation_on', type=int)
    args = parser.parse_args()
    if args.evaluation_on is not None:
        if args.evaluation_on != 0 and args.evaluation_on != 1:
            raise Exception('Select 0 or 1 for evaluation_on')
        else:
            evaluation_on = args.evaluation_on
    pr_kw = np.load('temp/pianoroll.npz')
    # pr_label_sum = np.sum(pr_kw['prref'], 2)
    # pr_label_sum[pr_label_sum > 1] = 1
    # fig1, fig2 = plt_pianoroll_comparison(pr_kw['prest'], pr_label_sum)
    # fig1.savefig('temp/pianoroll_est.png')
    # fig2.savefig('temp/pianoroll_ref.png')
    fig1 = plt_pianoroll(pr_kw['prest'])
    fig1.savefig('temp/pianoroll_est.png')
    if evaluation_on == 1:
        pr_label_sum = np.sum(pr_kw['prref'], 2)
        pr_label_sum[pr_label_sum > 1] = 1
        fig2 = plt_pianoroll(pr_label_sum)
        fig2.savefig('temp/pianoroll_ref.png')
