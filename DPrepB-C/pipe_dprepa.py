#!/usr/bin/env python

import os
import time as t
import subprocess
import argparse

import numpy as np

from processing_components.image.operations import import_image_from_fits, export_image_to_fits, qa_image
from processing_components.visibility.operations import append_visibility

from ska_sip.metamorphosis.filter import uv_cut, uv_advice
from ska_sip.telescopetools.initinst import init_inst
from ska_sip.accretion.ms import load
from ska_sip.pipelines.dprepa import dprepa_imaging, arl_data_future

import dask
import dask.array as da
from dask.distributed import Client
from distributed.diagnostics import progress
from distributed import wait

__author__ = "Jamie Farnes"
__email__ = "jamie.farnes@oerc.ox.ac.uk"


"""
This code is something of a "Workflow Script Wrapper".

Execution control would load this code. At the moment, Execution Control is essentially 'python -i pipe.py'!
"""


def main(args):
    """
    Initialising launch sequence.
    """
    # ------------------------------------------------------
    # Print some stuff to show that the code is running:
    print("")
    os.system("printf 'A demonstration of a \033[5mDPrepA\033[m SDP pipeline\n'")
    print("")
    # Set the directory for the moment images:
    MOMENTS_DIR = args.outputs + '/MOMENTS'
    # Check that the output directories exist, if not then create:
    os.makedirs(args.outputs, exist_ok=True)
    os.makedirs(MOMENTS_DIR, exist_ok=True)
    # Set the polarisation definition of the instrument:
    POLDEF = init_inst(args.inst)
    
    # Setup Variables for SIP services
    # ------------------------------------------------------
    # Define the Queue Producer settings:
    if args.queues:
        queue_settings = {'bootstrap.servers': '10.60.253.31:9092', 'message.max.bytes': 100000000}
    
    # Setup the Confluent Kafka Queue
    # ------------------------------------------------------
    if args.queues:
        from confluent_kafka import Producer
        import pickle
        # Create an SDP queue:
        sip_queue = Producer(queue_settings)
    
    # Define a Data Array Format
    # ------------------------------------------------------
    def gen_data(channel):
        return np.array([vis1[channel], vis2[channel], channel, None, None, False, False, args.plots, float(args.uvcut), float(args.pixels), POLDEF, args.outputs, float(args.angres), None, None, None, None, None, None, args.twod, npixel_advice, cell_advice])
    
    # Setup the Dask Cluster
    # ------------------------------------------------------
    starttime = t.time()

    dask.config.set(get=dask.distributed.Client.get)
    client = Client(args.daskaddress)  # scheduler for Docker container, localhost for P3.
    
    print("Dask Client details:")
    print(client)
    print("")

    # Define channel range for 1 subband, each containing 40 channels:
    channel_range = np.array(range(int(args.channels)))

    # Load the data into memory:
    """
    The input data should be interfaced with Buffer Management.
    """
    print("Loading data:")
    print("")
    vis1 = [load('%s/%s' % (args.inputs, args.ms1), range(0, int(args.channels)), POLDEF)]
    vis2 = [load('%s/%s' % (args.inputs, args.ms2), range(0, int(args.channels)), POLDEF)]

    # Prepare Measurement Set
    # ------------------------------------------------------
    # Combine MSSS snapshots:
    vis_advice = append_visibility(vis1[0], vis2[0])
    
    # Apply a uv-distance cut to the data:
    vis_advice = uv_cut(vis_advice, float(args.uvcut))
    npixel_advice, cell_advice = uv_advice(vis_advice, float(args.uvcut), float(args.pixels))
    
    # Begin imaging via the Dask cluster
    # ------------------------------------------------------
    # Submit data for each channel to the client, and return an image:

    # Scatter all the data in advance to all the workers:
    """
    The data here could be passed via Data Queues.
    Queues may not be ideal. Data throughput challenges.
    Need to think more about the optimum approach.
    """
    print("Scatter data to workers:")
    print("")
    big_job = [client.scatter(gen_data(0))]

    # Submit jobs to the cluster and create a list of futures:
    futures = [client.submit(dprepa_imaging, big_job[0], pure=False, retries=3)]
    """
    The dprepb_imaging function could generate QA, logging, and pass this information via Data Queues.
    Queues work well for this.
    Python logging calls are preferable. Send them to a text file on the node.
    Run another service that watches that file. Or just read from standard out.
    The Dockerisation will assist with logs.
    """

    print("Imaging on workers:")
    # Watch progress:
    progress(futures)

    # Wait until all futures are complete:
    wait(futures)
    
    # Check that no futures have errors, if so resubmit:
    for future in futures:
        if future.status == 'error':
            print("ERROR: Future", future, "has 'error' status, as:")
            print(client.recreate_error_locally(future))
            print("Rerunning...")
            print("")
            index = futures.index(future)
            futures[index].cancel()
            futures[index] = client.submit(dprepa_imaging, big_job[index], pure=False, retries=3)

    # Wait until all futures are complete:
    wait(futures)

    # Gather results from the futures:
    results = client.gather(futures, errors='raise')

    # Run QA on ARL objects and produce to queue:
    if args.queues:
        print("Adding QA to queue:")
        for result in results:
            sip_queue.produce('qa', pickle.dumps(qa_image(result), protocol=2))

        sip_queue.flush()

    # Return the data element of each ARL object, as a Dask future:
    futures = [client.submit(arl_data_future, result, pure=False, retries=3) for result in results]

    progress(futures)

    wait(futures)

    endtime = t.time()
    print(endtime-starttime)


# Define the arguments for the pipeline:
ap = argparse.ArgumentParser()
ap.add_argument('-d', '--daskaddress', help='Address of the Dask scheduler [default scheduler:8786]', default='scheduler:8786')
ap.add_argument('-c', '--channels', help='Number of channels to process [default 40]', default=40)

ap.add_argument('-inp', '--inputs', help='Input data directory [default /data/inputs]', default='/data/inputs')
ap.add_argument('-out', '--outputs', help='Output data directory [default /data/outputs]', default='/data/outputs')
ap.add_argument('-ms1', '--ms1', help='Measurement Set 1 [default sim-1.ms]', default='sim-1.ms')
ap.add_argument('-ms2', '--ms2', help='Measurement Set 2 [default sim-2.ms]', default='sim-2.ms')
ap.add_argument('-q', '--queues', help='Enable Queues? [default False]', default=False)
ap.add_argument('-p', '--plots', help='Output diagnostic plots? [default False]', default=False)
ap.add_argument('-2d', '--twod', help='2D imaging [True] or wstack imaging [False]? [default False]', default=True)

ap.add_argument('-uv', '--uvcut', help='Cut-off for the uv-data [default 450]', default=450.0)
ap.add_argument('-a', '--angres', help='Force the angular resolution to be consistent across the band, in arcmin FWHM [default 8.0]', default=8.0)
ap.add_argument('-pix', '--pixels', help='The number of pixels/sampling across the observing beam [default 5.0]', default=5.0)
ap.add_argument('-ins', '--inst', help='Instrument name (for future use) [default LOFAR]', default='LOFAR')
args = ap.parse_args()
main(args)
