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
  conda env create -n MLCFP -f environment.yml
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
Under review
