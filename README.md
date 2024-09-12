# Multi-Layer Combined Frequency and Periodicity Representations for Multi-Pitch Estimation of Multi-Instrument Music
ML-CFP (Multi-Layer Combined Frequency and Periodicity) is an unsupervised multi-pitch estimation method.

## Usage
#### Install
  ```
  git clone https://github.com/TomokiMatsunaga/ML-CFP.git
  ```
  ```
  cd ML-CFP
  ```
  ```
  conda env create -f environment.yml
  ```
  ```
  conda activate MLCFP
  ```
- Install `PyTorch>=1.12` following the [official installation instructions](https://pytorch.org/get-started/locally/)
  

#### Prediction
  ```
  python MLCFP.py --evaluation_on 0
  ```
#### Evaluation
  ```
  python MLCFP.py --evaluation_on 1 --dataset 'dataset name'
  ```
#### Show pianoroll
  ```
  python pianoroll.py --evaluation_on 0
  ```
or
  ```
  python pianoroll.py --evaluation_on 1
  ```
## Citation
  ```
  @ARTICLE{10564134,
  author={Matsunaga, Tomoki and Saito, Hiroaki},
  journal={IEEE/ACM Transactions on Audio, Speech, and Language Processing}, 
  title={Multi-Layer Combined Frequency and Periodicity Representations for Multi-Pitch Estimation of Multi-Instrument Music}, 
  year={2024},
  volume={32},
  number={},
  pages={3171-3184},
  keywords={Frequency-domain analysis;Harmonic analysis;Multiple signal classification;Instruments;Cepstrum;Feature extraction;Training;Automatic music transcription;multi-pitch estimation;music signal processing;partial cepstrum},
  doi={10.1109/TASLP.2024.3416730}}
  ```
