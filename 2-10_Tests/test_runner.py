import time
import signal
import json
import subprocess
from termcolor import colored 

class Timer:
    def __init__(self):
        self._start_time = None

    def start(self):
        self._start_time = time.perf_counter()

    def stop(self):
        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        print(f'\tElapsed time: {elapsed_time:0.4f} seconds')

class SignalCatcher:
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True

def test_case(iteration):
    print(f'\n\nStarting iteration {iteration}:')
    
    # Use this timer to compute throughput benchmarking
    timer = Timer()
    
    # Make the file names we need to execute
    clean_file = f'test{iteration}.wgsl'
    ub_file = f'test{iteration}_ub.wgsl'
    json_file = f'test{iteration}_ub.json'

    # Fuzz a program and store it in clean_file
    print('\nFuzzing a kernel...')
    timer.start()
    subprocess.run(['wgslsmith', 'gen', '--recondition', '-o', clean_file])
    timer.stop()
    
    # Run clean_file with the correct configuration (dawn:vk:7857 or wgpu:vk7857) and check validity
    print('\nChecking for timeout...')
    timer.start()
    # TODO: Check for bounds of timeout (too fast? too long?) Lets try and be aggressive for now
    out = subprocess.run(['wgslsmith-harness', 'run', '--timeout', '6', '-c', 'dawn:vk:7857', clean_file], capture_output=True, text=True)
    if 'timeout' in out.stdout:
        print(colored('\tSlow Kernel', 'yellow'))
        subprocess.run(['rm', clean_file]) # Clean up
        timer.stop()
        return
    print(colored('\tKernel OK continuing', 'green'))
    timer.stop()

    # Insert flow
    print('\nInserting flow analysis...')
    timer.start()
    subprocess.run(['wgslsmith-flow', clean_file, clean_file])
    timer.stop()

    # Insert threading
    print('\nInserting threading...')
    timer.start()
    subprocess.run(['wgslsmith-thread', '-w', '32', clean_file, clean_file])
    timer.stop()

    # Run and pipe output to file clean.out (clean up extra lines here) NOTE: Assumption is that the last two steps don't change
    # execution time
    print('\nGetting baseline output...')
    timer.start()
    clean_out = open('clean.out', 'w')
    subprocess.run(['wgslsmith-harness', 'run', '-c', 'dawn:vk:7857', clean_file], stdout=clean_out)
    timer.stop()

    # Insert UB

    # Run and pipe output to file ub.out (clean up extra lines here) TODO: We might be interested in the data stored in 0:4

    # Use Linux diff tool and save mismatches, delete non-mismatches

# TODO: Keep track of execution stats (would be nice to know how many timeouts we get so we can optimize the timeout bounds)
if __name__ == "__main__":
    catcher = SignalCatcher()
    total_timer = Timer()

    # Grab itertion from json if it exists else set iter to 0
    try:
        fp = open('.state.json', 'r')
        iteration = json.load(fp)['iter']
        fp.close()
    except:
        iteration = 0
    
    while not catcher.kill_now:
        iteration += 1 # Increment before to protect on exit
        total_timer.start()
        test_case(iteration)
        print('\nTotal test time is: ', end='')
        total_timer.stop()
        # Do tests

    # Exited loop gracefully save state here
    fp = open('.state.json', 'w')
    json.dump({'iter': iteration},  fp)
    fp.close()
    print("State saved, run again to continue tests")
