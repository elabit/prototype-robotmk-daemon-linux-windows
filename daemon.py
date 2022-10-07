#!/usr/bin/env/python
# SPDX-FileCopyrightText: © 2022 ELABIT GmbH <mail@elabit.de>
# SPDX-License-Identifier: GPL-3.0-or-later


import sys, os, time, atexit, signal
import platform
from abc import ABC, abstractmethod
from pathlib import Path
import re

daemon_py = "daemon.py"


class ForkStrategy(ABC):
    def __init__(self, daemon):
        self.daemon = daemon

    @abstractmethod
    def daemonize(self):
        pass


class LinuxStrategy(ForkStrategy):
    def daemonize(self):

        try:
            # FORK I) the child process
            pid = os.fork()
            if pid > 0:
                # exit the parent process
                sys.exit(0)
        except OSError as err:
            sys.stderr.write("fork #1 failed: {0}\n".format(err))
            sys.exit(1)

        # executed as child process
        # decouple from parent environment, start new session
        # with no controlling terminals
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # FORK II) the grandchild process
        try:
            pid = os.fork()
            if pid > 0:
                # exit the child process
                sys.exit(0)
        except OSError as err:
            sys.stderr.write("fork #2 failed: {0}\n".format(err))
            sys.exit(1)

        # here we are the grandchild process,
        # daemonize it, connect fds to /dev/null stream
        sys.stdout.flush()
        sys.stderr.flush()
        si = open(os.devnull, "r")
        so = open(os.devnull, "a+")
        se = open(os.devnull, "a+")

        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())


class WindowsStrategy(ForkStrategy):
    def daemonize(self):
        # On Windows, no double fork is needed (Dameon is already started detached)
        pass


class Daemon:
    def __init__(self, pidfile):
        if not pidfile:
            tmpdir = Path(os.getenv("TEMP", "/tmp"))
            pidfile = "%s.pid" % daemon_py
            self.pidfile = tmpdir / pidfile
        else:
            self.pidfile = Path(pidfile)
        if platform.system() == "Linux":
            self.fork_strategy = LinuxStrategy(self)
        elif platform.system() == "Windows":
            self.fork_strategy = WindowsStrategy(self)

    def daemonize(self):
        self.fork_strategy.daemonize()
        self.write_and_register_pidfile()

    @property
    def pid(self):
        return str(os.getpid())

    def get_pid_from_file(self):
        try:
            with open(self.pidfile, "r") as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None
        return pid

    def delpid(self):
        os.remove(self.pidfile)

    def write_and_register_pidfile(self):
        with open(self.pidfile, "w+") as f:
            f.write(self.pid + "\n")
        atexit.register(self.delpid)

    def start(self):
        # Check for a pidfile to see if the daemon already runs
        pid = self.get_pid_from_file()

        if pid:
            msg = "One instance of %s is already running (PID: %d).\n" % (
                daemon_py,
                int(pid),
            )
            sys.stderr.write(msg.format(self.pidfile))
            sys.exit(1)
        else:
            # daemonize according to the strategy
            self.daemonize()
            # Do the work
            self.run()

    def stop(self):
        # Check for a pidfile to see if the daemon already runs
        pid = self.get_pid_from_file()

        if not pid:
            message = "pidfile {0} does not exist. " + "Daemon does not seem to run.\n"
            sys.stderr.write(message.format(self.pidfile))
            return  # not an error in a restart

        # Try killing the daemon process
        try:
            while 1:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)
        except OSError as err:
            e = str(err.args)
            # e = "(22, 'Falscher Parameter', None, 87, None)"
            # kommt manchmal - abfangen: (13, 'Zugriff verweigert', None, 5, None)
            if e.find("No such process") > 0 or re.match(".*22.*87", e):
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print(str(err.args))
                sys.exit(1)

    def restart(self):
        """Restart the daemon."""
        self.stop()
        self.start()

    def run(self):
        """You should override this method when you subclass Daemon.

        It will be called after the process has been daemonized by
        start() or restart()."""


class MyDaemon(Daemon):
    def __init__(self, pidfile=None):
        super().__init__(pidfile)

    def run(self):
        while True:
            # DUMMY DAEMON CODE
            print("Daemon is running ... ")
            time.sleep(1)


def usage():
    print("Usage: %s start|stop|restart" % sys.argv[0])


if __name__ == "__main__":
    daemon = MyDaemon()
    if len(sys.argv) == 2:
        if "start" == sys.argv[1]:
            daemon.start()
        elif "stop" == sys.argv[1]:
            daemon.stop()
        elif "restart" == sys.argv[1]:
            daemon.restart()
        else:
            usage()
            sys.exit(2)
        sys.exit(0)
    else:
        usage()
        sys.exit(2)
