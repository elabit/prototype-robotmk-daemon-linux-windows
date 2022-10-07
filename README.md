# Daemonizing a script on Windows and Linux

This repo is a prototype for later running Robotmk on Windows and Linux operating systems. 

## Requirements to be met

- Robotmk should be able to independently launch test suites according to their individual schedules. Parallel execution should also be allowed. 
- An alternative way to execute Robotmk asynchronously has to be found (see also: https://github.com/elabit/robotmk/blob/develop/FAQ.md#asnychronous-execution-and-scheduling). 
- The execution of robot suites must be independent from the agent under all circumstances, so that e.g. a premature termination (e.g. by timeout) is not possible. (see also here: https://github.com/elabit/robotmk/blob/develop/FAQ.md#asnychronous-execution-and-scheduling)
- To fulfil the requirement of independency, the daemon process must be created as a separate process on it's own (instead of being a subprocess of `daemon_ctrl.py`, which would also terminate its subprocess on exit)
- There must be a guarantee that a crashing background process can be restarted in case of a failure. 
- Don't abuse cache files (only Linux) which could be touched in order to keep an async plugin running as a daemon
- The mechanism should work for Windows and Linux

## No-Gos

- Deployment of one PLugin per suite, parameterization via name components. 
- Installation of an additional system component and/or technology on Agentemn side (e.g. of a Window services or Systemd service).

## Implementation: 

### Scripts 

- `daemon.py` is the script that will later run in the background as a daemon and continuously start so-called "runner" subprocesses (not part of this project), which in turn call one or more robot suites simultaneously. Each runner terminates only when all of its subprocesses have terminated. Therefore it is also allowed that several runners started at different times run simultaneously.
- `daemon_ctrl.py` is started asynchronously (maybe synchronously?) in short intervals (e.g. 1-2min) by the CMK agent. This script has only the task to start the daemon (if it is not already running). 

### How it works on Windows and Linux

It turned out that the implementation in order to start a detached daemon has to be done differently for Windows and Linux: 

- On Linux, one can use the "[double fork](http://thelinuxjedi.blogspot.com/2014/02/why-use-double-fork-to-daemonize.html)" method, where a process can completely decouple itself from the terminal of the parent process by double forking. 
- The Windows kernel, however, does not know such a "fork" method. Instead, it is possible to use "[Process Creation flags](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags)" during the process creation that this is not a subprocess, but started in a new process group and thus becomes an independent root process. 

These two mechanisms - double fork (linux) and process creation flags - are used in this project. 


| No  | Description           | Action            | Windows                                                              | Linux                                                                                   |
| --- | --------------------- | ----------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| A   | Start daemon by ctrl  | `daemon_ctrl.py`  | creates detached process for `daemon.py`, which runs **daemonized**. | creates a subprocess for `daemon.py`, which itself double-forks and runs **damonized**. |
| B   | Start daemon natively | `daemon.py start` | ⚠️ starts the daemon in **foreground** because it cannot fork itself  | `daemon.py` double-forks and runs **daemonized**.                                       |
| a   | Stop daemon           | `daemon.py stop`  | stops the daemonized process (Ctrl-C if in foreground)               | stops the daemonized process (Ctrl-C if in foreground)                                  |

Notes: 

- A) `daemon_ctrl.py` is what will be executed by the Checkmk agent in regular intervals
- B) only for debugging
- a) ...? just for completeness. 

--- 

## Further considerations

### Checkmk Agent gets stopped 

As soon as the CMK agent is not running anymore, there is no guarantee that the daemon is kept running (nothing will attempt to re-start it).  
Thus, better than leaving the daemon in an undetermined state, we should take it as fact that a stopped Checkmk agent also should mean that the daemon has to be stopped. 

But because of the fact that both Linux and Windows agents have a complete different architecture, it is hard to find a native, OS independent way in which the agent could indicate if it is started or stopped. 

A possible solution could be a "dead man switch" functionality:  
`daemon_ctrl.py` periodically touches a state file. `daemon.py` would exit as soon as it detects that the state file is too old.  
In this way, we would have reached a "parent-child pseudo dependency" between the `daemon_ctrl` and the `daemon` itself, without having a real process dependency. 

## Running test with UI access

Robotmk mode "*external*" was build to let the `robotmk-runner.py` script be executed by the Windows Task Scheduler. In this way, the Robot process has access to the user's desktop and is able to start GUI applications there.  
Until today, this mode is exclusive to the mode "*agent_serial*", where Robotmk is triggered asynchronously by the Agent (and running under SYSTEM context, without desktop access). Both modes have their reasons, but are not mixable per host. 

In future, the mode could be selected on a suite basis. If there is really a need to run tests both headless and others with desktop access, two daemons are running, each executing their set of suites: 

- `CMK Agent --> daemon_ctrl.py --> daemon.py --> robotmk-runner.py --> 1..n suites (SYSTEM)`
- `Task Scheduler --> daemon_ctrl.py --> daemon.py --> robotmk-runner.py --> 1..n suites (USER)`

Here, as in general with multiprocessing exeuctions of Robotmk, concurrent log file access has to be ensured. 