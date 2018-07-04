# Set the base image
FROM daskdev/dask-notebook

# Dockerfile author 
MAINTAINER Jamie Farnes <jamie.farnes@oerc.ox.ac.uk>

# As root, set up a python3.5 conda environment, activate, and install dask:
USER root
RUN mkdir sdp
RUN conda install python=3.5 && conda install dask distributed && conda install setuptools && conda install numpy && conda install -c conda-forge matplotlib && conda install -c conda-forge casacore && conda install -c conda-forge python-casacore

# As root, install various essential packages
RUN apt-get update && apt-get install -y graphviz git && apt-get -y install build-essential && apt-get -y install libssl-dev libffi-dev

# Install precursors to git-lfs and kernsuite
RUN sudo apt-get -y install software-properties-common
RUN apt-get -y install curl

# Install git-lfs
RUN curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
RUN apt-get -y install git-lfs
RUN git lfs install

# Set working directory
WORKDIR /home/jovyan/sdp

# Download the SIP DPrepB-C pipeline
RUN git clone https://github.com/jamiefarnes/SKA-SIP-DPrepB-C-Pipeline

# Download the RMextract repository
RUN git clone https://github.com/lofar-astron/RMextract

# Download the SKA Algorithm Reference Library (ARL)
RUN git clone https://github.com/SKA-ScienceDataProcessor/algorithm-reference-library &&\
    cd ./algorithm-reference-library/ && python setup.py install &&\
    git-lfs pull &&\
    rm -rf ./data/vis &&\
    rm -rf ./data/models &&\
    rm -rf ./.git

# Set the environment variables in advance of python installs:
ENV PYTHONPATH=$PYTHONPATH:/home/jovyan/sdp/algorithm-reference-library/:/opt/conda/lib/python3.5/site-packages/:/usr/lib/python3/dist-packages/

# Download the requirements for ARL
# and uninstall conflicting version of numpy and reinstall
# and downgrade astropy to a version compatible with Aegean
WORKDIR /home/jovyan/sdp/algorithm-reference-library
RUN pip install -r requirements.txt &&\
    pip uninstall -y numpy &&\
    pip uninstall -y astropy &&\
    conda install numpy &&\
    conda install astropy==2.0.6

# Setup/install the SIP MAPS Pipeline
WORKDIR /opt/conda/lib/python3.5/
RUN ln -s ~/sdp/SKA-SIP-DPrepB-C-Pipeline/DPrepB-C/ska_sip

# Setup/install RMextract
WORKDIR /home/jovyan/sdp/RMextract
RUN python setup.py build
RUN python setup.py install

WORKDIR /opt/conda/lib/python3.5/
RUN ln -s ~/sdp/algorithm-reference-library/data
RUN ln -s ~/sdp/algorithm-reference-library/data_models
RUN ln -s ~/sdp/algorithm-reference-library/processing_components
RUN ln -s ~/sdp/algorithm-reference-library/libs
RUN ln -s ~/sdp/algorithm-reference-library/workflows

# Define initial working directory
WORKDIR /home/jovyan/sdp/
