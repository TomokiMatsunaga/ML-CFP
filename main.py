from MLCFP import extract_evaluation, extraction_detail_eval


if __name__ == '__main__':
    extract_evaluation('MAPS/ENSTDkCl/MUS/*.wav', 'MAPS/ENSTDkCl/MUS/',
                       dataset='MAPS', instrument_wise=1, instlist=[1], length=30)
    extraction_detail_eval('temp/comp/*.npz', 'temp/label/', 'temp/detail_eval.csv')


