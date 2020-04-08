#! /usr/bin/env python

import sys
from aubio import tempo, source
import numpy as np
import logging
from itertools import count
import time

from pysoundcard import Stream




def ms_time():
    return int(time.time() * 1000.0)

def ms_time_with_ms_offset(start_time, offset_ms):
    return int(start_time + offset_ms)

log = lambda *x: logging.warning(f"{ms_time()} : {x}")


def stream_to_bpm(audio_stream, samplerate, hop_s, buffer_size):
    o = tempo("default", buffer_size, hop_s, samplerate)

    # tempo detection delay, in samples
    # default to 4 blocks delay to catch up with
    delay = 4. * hop_s

    # list of beats, in samples
    beats = []

    latencies = []

    last_period_start = None

    try:
        while True:
            samples = stream.read(hop_s)
            samples = samples.sum(-1) / float(stream.channels[0])
            is_beat = o(samples)
            
            if is_beat:
                this_beat = o.get_last_s()
                beats.append(this_beat)

            if len(beats) > 15:
                bpms = 60. / np.diff(beats)
                bpm = np.median(bpms)
                beats = beats[1:]
                log('bpm', bpm)
                now = ms_time()

                if last_period_start is None:
                    last_period_start = ms_time()

                if last_period_start <= now:
                    l = last_period_start
                    last_period_start = now
                    offset_one_beat = (60.0 / (bpm * 1.0) ) * 4000.0
                    last_period_start = ms_time_with_ms_offset(last_period_start, offset_one_beat)
                    cur_latency = now - l
                    latencies.append(cur_latency)
                  
                    log('pred', last_period_start, cur_latency)


    except:
        log("error")
    stream.close()
    for late in latencies:
        print(late)
    avg_latency = np.mean(latencies) / 4.0
    med_latency = np.median(latencies) / 4.0

    print("avg", avg_latency, med_latency)

        




# open stream
buffer_size = 1024
hop_size = buffer_size // 2

n_channels = 1
samplerate = 44100
stream = Stream(blocksize = hop_size, channels = 1)
stream.start()



stream_to_bpm(stream, samplerate, hop_size, buffer_size)