#!/usr/bin/env python

"""dprepb.py: The DPrepB/C imaging pipeline for SIP."""

import sys
import os

os.makedirs('LOGS', exist_ok=True)
sys.stdout = open('%s/dprepb-log.txt' % ('LOGS'), 'w')

import numpy as np

import subprocess

from data_models.polarisation import PolarisationFrame

from processing_components.imaging.base import create_image_from_visibility, advise_wide_field
from processing_components.image.operations import export_image_to_fits
from processing_components.visibility.operations import append_visibility
from processing_components.image.deconvolution import restore_cube

from ska_sip.metamorphosis.filter import uv_cut, uv_advice
from ska_sip.metamorphosis.convert import convert_to_stokes
from ska_sip.metamorphosis.beam import beam_me_up, apply_station_beams
from ska_sip.outflows.images.imaging import wstack, image_2d
from ska_sip.outflows.images.deconvolution import deconvolve_cube_complex
from ska_sip.outflows.rmsynthesis.rmsynth import load_im_data, rmsynth_advice, do_rmsynth, rmcube_save_to_disk
from ska_sip.outflows.rmsynthesis.rmclean import rmclean_prep, do_rmclean
from ska_sip.outflows.moments.moments import load_moments_data, calc_moments, moments_save_to_disk
from ska_sip.eventhorizon.plot import uv_cov, uv_dist, plt_rmsf

sys.stdout.close()
sys.stdout = sys.__stdout__

__author__ = "Jamie Farnes"
__email__ = "jamie.farnes@oerc.ox.ac.uk"


def dprepb_imaging(vis_input):
    """Do DPrepB/C imaging of visibility data.
        
    Args:
    vis_input (array): data array of ARL visibility data and parameters.
    
    Returns:
    restored: clean image.
    """
    # Load the Input Data
    # ------------------------------------------------------
    vis1 = vis_input[0]
    vis2 = vis_input[1]
    channel = vis_input[2]
    stations = vis_input[3]
    lofar_stat_pos = vis_input[4]
    APPLY_IONO = vis_input[5]
    APPLY_BEAM = vis_input[6]
    MAKE_PLOTS = vis_input[7]
    UV_CUTOFF = vis_input[8]
    PIXELS_PER_BEAM = vis_input[9]
    POLDEF = vis_input[10]
    RESULTS_DIR = vis_input[11]
    FORCE_RESOLUTION = vis_input[12]
    ionRM1 = vis_input[13]
    times1 = vis_input[14]
    time_indices1 = vis_input[15]
    ionRM2 = vis_input[16]
    times2 = vis_input[17]
    time_indices2 = vis_input[18]
    twod_imaging = vis_input[19]
    
    # Make a results directory on the worker:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Redirect stdout, as Dask cannot print on workers
    # ------------------------------------------------------
    sys.stdout = open('%s/dask-log.txt' % (RESULTS_DIR), 'w')
    
    # Prepare Measurement Set
    # ------------------------------------------------------
    # Combine MSSS snapshots:
    vis = append_visibility(vis1, vis2)
    
    # Apply a uv-distance cut to the data:
    vis = uv_cut(vis, UV_CUTOFF)
    npixel_advice, cell_advice = uv_advice(vis, UV_CUTOFF, PIXELS_PER_BEAM)
    
    # Make some basic plots:
    if MAKE_PLOTS:
        uv_cov(vis)
        uv_dist(vis)
    
    # Primary Beam Correction
    # ------------------------------------------------------
    # Apply the primary beam of the instrument:
    if APPLY_BEAM:
        beams = beam_me_up(INPUTS_DIR, MS1)  # use only one MS (each MS should have identical station positions, phase centre, etc.)
        vis = apply_station_beams(vis, beams, channel)

    # Imaging and Deconvolution
    # ------------------------------------------------------
    # Convert from XX/XY/YX/YY to I/Q/U/V:
    vis = convert_to_stokes(vis, POLDEF)

    # Image I, Q, U, V, per channel:
    if twod_imaging:
        dirty, psf = image_2d(vis, npixel_advice, cell_advice, channel, RESULTS_DIR)
    else:
        dirty, psf = wstack(vis, npixel_advice, cell_advice, channel, RESULTS_DIR)

    # Deconvolve (using complex Hogbom clean):
    comp, residual = deconvolve_cube_complex(dirty, psf, niter=100, threshold=0.001, fracthresh=0.001, window_shape='', gain=0.1, algorithm='hogbom-complex')

    # Convert resolution (FWHM in arcmin) to a psfwidth (standard deviation in pixels):
    clean_res = (((FORCE_RESOLUTION/2.35482004503)/60.0)*np.pi/180.0)/cell_advice

    # Create the restored image:
    restored = restore_cube(comp, psf, residual, psfwidth=clean_res)

    return restored


def arl_data_future(restored):
    """Return the data from an ARL object.
        
    Args:
    restored (ARL object): ARL image data.
    
    Returns:
    restored.data: clean image.
    """
    
    return restored.data
