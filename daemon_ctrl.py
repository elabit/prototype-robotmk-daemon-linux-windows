#!/usr/bin/env/python
# SPDX-FileCopyrightText: © 2022 ELABIT GmbH <mail@elabit.de>
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys
import signal
import subprocess
from pathlib import Path
import platform
import psutil
import re
from abc import ABC, abstractmethod

daemon_py = "daemon.py"

interpreter = sys.executable
thisdir = Path(os.path.dirname(os.path.abspath(__file__)))
program = thisdir / daemon_py


def main():
    # Windows:
    # - calls daemon as a DETACHED daemon process
    # - daemon.py recognizes OS=Windows, will not double fork itself (runs already detached)
    # - it is NOT possible to run the daemon directly with "daemon.py start" - it
    #   will start, but remain in its own process, without detaching.
    # Linux:
    # - calls daemon as normal process
    # - daemon.py will double fork (forks itself and then exits)

    daemon_ctrl = DaemonCtrl()

    if not daemon_ctrl.is_daemon_running():
        daemon_ctrl.create_process()


class DaemonCtrl:
    def __init__(self):
        self.proc_pattern = ".*python.*%s" % daemon_py
        pidfile = daemon_py + ".pid"
        self.daemon_pidfile = Path(os.getenv("TEMP", "/tmp")) / pidfile

        if platform.system() == "Linux":
            self.strategy = LinuxStrategy()
        elif platform.system() == "Windows":
            self.strategy = WindowsStrategy()

    def is_daemon_running(self):
        """Checks daemon existence in two ways:
        - is process runing
        - is statefile present
        and does the housekeeping.
        """
        processes = self.get_process_list()
        pid = self.get_pid_from_file()

        if len(processes) == 0:
            print("No processes are running.")
            if pid:
                self.unlink_pidfile()
            return False
        elif len(processes) == 1:
            # One instance is running
            if pid:
                print(
                    "One instance of %s is already running (PID: %d)."
                    % (daemon_py, int(pid))
                )
                return True
            else:
                print(
                    "One instance of %s is already running, but no PID file found."
                    % daemon_py
                )
                print("Cleaning up.")
                # Instance without PID file
                self.kill_all(processes)
                return False
        elif len(processes) > 1:
            print("More than one instance of %s is running." % daemon_py)
            print("Cleaning up.")
            # fucked up, clean all
            self.kill_all(processes)
            self.unlink_pidfile()
            return False

    def unlink_pidfile(self):
        """Deletes the PID file"""
        if os.path.exists(self.daemon_pidfile):
            os.remove(self.daemon_pidfile)

    def kill_all(self, processes):
        for process in processes:
            os.kill(process["pid"], signal.SIGTERM)

    def get_process_list(self):
        """Returns a list of Process objects matching the search pattern"""
        listOfProcessObjects = []
        # Iterate over the all the running process
        for proc in psutil.process_iter():
            try:
                pinfo = proc.as_dict(attrs=["pid", "name", "cmdline"])
                # Check if process name contains the given name string.
                if pinfo["cmdline"] and re.match(
                    self.proc_pattern, " ".join(pinfo["cmdline"])
                ):
                    listOfProcessObjects.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return listOfProcessObjects

    def get_pid_from_file(self):
        """Reads PID from pidfile, returns None if not found"""
        try:
            with open(self.daemon_pidfile, "r") as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None
        return pid

    def create_process(self):
        self.strategy.create_process()


class SubprocesStrategy(ABC):
    @abstractmethod
    def create_process(self):
        pass


class LinuxStrategy(SubprocesStrategy):
    creationflags = None

    def create_process(self):
        print("Starting daemon...")
        process = subprocess.Popen([interpreter, program, "start"], self.creationflags)
        print(
            "Started! PID = {} (linux double fork will create another one)".format(
                process.pid
            )
        )


class WindowsStrategy(SubprocesStrategy):
    flags = 0
    flags |= 0x00000008  # DETACHED_PROCESS
    flags |= 0x00000200  # CREATE_NEW_PROCESS_GROUP
    flags |= 0x08000000  # CREATE_NO_WINDOW

    pkwargs = {
        "close_fds": True,  # close stdin/stdout/stderr on child
        "creationflags": flags,
    }

    def create_process(self):
        print("Starting daemon...")
        process = subprocess.Popen([interpreter, program, "start"], **self.pkwargs)
        print("Started! Daemon PID = {}".format(process.pid))


if __name__ == "__main__":
    main()
