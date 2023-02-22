import time
import signal
import json
import subprocess
import random
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
    # TODO: Fix overhead and increase threads
    subprocess.run(['wgslsmith-thread', '-w', '16', clean_file, clean_file])
    timer.stop()

    # Run and pipe output to file clean.out (clean up extra lines here) NOTE: Assumption is that the last two steps don't change
    # execution time
    print('\nGetting baseline output...')
    timer.start()

    out = subprocess.run(['wgslsmith-harness', 'run', '--timeout', '10', '-c', 'dawn:vk:7857', clean_file], capture_output=True, text=True)
    if 'timeout' in out.stdout:
        print(colored('\tSlow Kernel', 'yellow'))
        subprocess.run(['rm', clean_file]) # Clean up
        timer.stop()
        return
    with open('clean.out', 'w') as f:
        f.write(out.stdout)

    print(colored('\tKernel OK continuing', 'green'))
    timer.stop()

    # Insert UB
    print('\nInserting undefined behavior...')
    timer.start()
    subprocess.run(['wgslsmith-ub', '-c', '20', clean_file, ub_file])
    # Write the UB json file here (TODO: Make this smarter)
    low_bound = random.randint(65, 127)
    up_bound = random.randint(127,132)
    json_data = f'{{\n"0:0": [{low_bound},0,0,0,{up_bound},0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0]\n}}'
    with open(json_file, 'w') as f:
        f.write(json_data)
    timer.stop()


    # Run and pipe output to file ub.out (clean up extra lines here) TODO: We might be interested in the data stored in 0:4
    print('\nGetting UB output...')
    timer.start()

    out = subprocess.run(['wgslsmith-harness', 'run', '--timeout', '10', '-c', 'dawn:vk:7857', ub_file], capture_output=True, text=True)
    if 'timeout' in out.stdout:
        print(colored('\tSlow Kernel', 'yellow'))
        subprocess.run(['rm', clean_file]) # Clean up
        subprocess.run(['rm', ub_file])
        timer.stop()
        return
    with open('ub.out', 'w') as f:
        f.write(out.stdout)

    print(colored('\tKernel OK continuing', 'green'))
    timer.stop()

    # For now use Grep, lets get timing on this tomorrow (TODO)
    print('\nComparing outputs...')
    timer.start()
    clean_out1 = subprocess.run(['grep', '0:1', 'clean.out'], capture_output=True, text=True).stdout
    clean_out2 = subprocess.run(['grep', '0:2', 'clean.out'], capture_output=True, text=True).stdout
    ub_out1 = subprocess.run(['grep', '0:1', 'ub.out'], capture_output=True, text=True).stdout
    ub_out2 = subprocess.run(['grep', '0:2', 'ub.out'], capture_output=True, text=True).stdout

    if clean_out1 != ub_out1 or clean_out2 != ub_out2:
        # Mismatch
        subprocess.run(['mkdir', f'mismatch{iteration}'])
        # Move all relevant files to mismatch
        subprocess.run(['mv', clean_file, ub_file, json_file, 'clean.out', 'ub.out', f'mismatch{iteration}'])
        # Move mismatch to flagged
        subprocess.run(['mv', f'mismatch{iteration}', 'flagged'])
        print(colored('\tMismatch', 'red')) 
    else:
        # Clean up
        print(colored('\tOk, cleaning up', 'green'))
        subprocess.run(['rm', clean_file, ub_file, json_file, 'clean.out', 'ub.out'])

    timer.stop()

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

    # Exited loop gracefully save state here
    fp = open('.state.json', 'w')
    json.dump({'iter': iteration},  fp)
    fp.close()
    print("State saved, run again to continue tests")
