import sys
import numpy as np
import logging
import logging

logging.basicConfig(level=logging.DEBUG, filename="/tmp/auditraq.log")


logger = logging.getLogger(__file__)
from itertools import count
from time import time
from threading import Thread
import multiprocessing
import signal


def ms_time():
    return int(time() * 1000.0)


def ms_time_with_ms_offset(start_time, offset_ms):
    return int(start_time + offset_ms)


# OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
def bpm_worker(
    event,
    osc_queue,
    audio_input_id,
    buffer_size=1024,
    samplerate=44100,
    beats_buffer_size=4,
):
    import soundcard as sc
    from aubio import tempo, source

    logger.debug("running bpm worker")

    class BPMThread(Thread):
        def run(self):
            while not event.wait(current_beat_length_in_second + skew_s):
                local_now = ms_time()
                if len(local_beat_times) > beat_times_size:
                    local_beat_times.pop(0)
                local_beat_times.append(local_now)
                osc_queue.put(("/beat/cleaned", (str(local_now),)))
                logger.debug(f"send osc: /beat/cleaned {local_now}")

    bpm_thread = BPMThread()

    blocksize = buffer_size // 2

    # tempo detection delay, in samples
    # default to 4 blocks delay to catch up with
    delay = (4.0 * blocksize) / samplerate

    current_beat_length_in_second = 0.5
    beats = []
    skew_s = 0
    global_beat_times = []
    local_beat_times = []

    beat_times_size = 8
    last_period_start = None

    logger.debug("starting audio")

    audio_input = sc.get_microphone(audio_input_id)
    logger.debug("got default")
    tempo_analyzer = tempo("default", buffer_size, blocksize, samplerate)

    with audio_input.recorder(blocksize=blocksize, samplerate=samplerate) as mic:
        logger.debug("got mic")

        while not event.is_set():
            samples = mic.record(numframes=blocksize)
            samples = samples.sum(axis=1) / float(audio_input.channels)
            samples = np.float32(samples)

            is_beat = tempo_analyzer(samples)
            now = ms_time()

            if is_beat:
                this_beat = tempo_analyzer.get_last_s()
                beats.append(this_beat)
                # logging.info(f"is beat: {is_beat}")
                osc_queue.put(("/beat/raw", (str(now),)))
                logger.debug(f"send osc: /beat/raw {now}")

                global_beat_times = global_beat_times[-beat_times_size:] + [now]

                # find closest similar beat and calculate diff
                skew_s = 0
                if len(local_beat_times) > 2:
                    local_ts = local_beat_times[-2]
                    times_array = np.array(global_beat_times)

                    most_similar = times_array[np.abs(times_array - local_ts).argmin()]
                    ts_diff_ms = abs(most_similar - local_ts)
                    if ts_diff_ms < current_beat_length_in_second * 1000.0:
                        sign = 0.001
                        if local_ts > most_similar:
                            sign *= -1
                        skew_s = sign * (ts_diff_ms * 0.1)

            if len(beats) > beats_buffer_size:
                bpms = 60.0 / np.diff(beats)
                bpm = np.median(bpms)
                beats = beats[1:]

                osc_queue.put(("/bpm", (bpm,)))
                current_beat_length_in_second = 60.0 / bpm

                if last_period_start is None:
                    last_period_start = now
                    bpm_thread.start()

                if last_period_start <= now:
                    l = last_period_start
                    last_period_start = now
                    offset_one_beat = (60.0 / (bpm * 1.0)) * 4000.0
                    last_period_start = ms_time_with_ms_offset(
                        last_period_start, offset_one_beat
                    )
                    cur_latency = now - l

                    osc_queue.put(("/next_beat", (str(last_period_start),)))
                    osc_queue.put(("/latency", (f"{cur_latency} {cur_latency-delay}",)))

    logger.debug("bpm exiting")


from pythonosc import udp_client
from pythonosc import osc_bundle_builder
from pythonosc import osc_message_builder


def osc_worker(event, queue, ip, port, bundle_size=10):
    logger.debug(f"creating client for ip:{ip} and port:{port}")
    client = udp_client.SimpleUDPClient(ip, port)

    while not event.is_set():
        bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
        messages_in_bundle = 0
        for i in range(bundle_size):
            try:
                address, values = queue.get_nowait()
            except:
                break
            msg = osc_message_builder.OscMessageBuilder(address=address)
            for value in values:
                msg.add_arg(value)
            bundle.add_content(msg.build())
            messages_in_bundle += 1
        if messages_in_bundle:
            bundle = bundle.build()
            client.send(bundle)
    logger.debug("osc client worker exiting")


def main(ip, port, audio_input_id):
    def handle_exit():
        raise SystemExit()

    signal.signal(signal.SIGTERM, handle_exit)

    osc_queue = multiprocessing.Queue()
    shutdown_event = multiprocessing.Event()

    osc_process = multiprocessing.Process(
        target=osc_worker, args=(shutdown_event, osc_queue, ip, port, 10)
    )
    osc_process.start()

    bpm_process = multiprocessing.Process(
        target=bpm_worker, args=(shutdown_event, osc_queue, audio_input_id)
    )
    bpm_process.start()

    try:
        while not shutdown_event.wait(1):
            pass
    except (KeyboardInterrupt, SystemExit) as e:
        logging.debug("exiting gracefully")
    finally:
        shutdown_event.set()
        osc_process.join()
        bpm_process.join()
        logger.debug("all worker processes are shut down")


if __name__ == "__main__":
    ip, port, microphone_id = sys.argv[1:]
    try:
        logger.info(f"port{port}")
        main(ip, int(port), int(microphone_id))
    except:
        logger.exception("err")
