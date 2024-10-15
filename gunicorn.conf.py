"""
Override these values in each service's gunicorn.conf.py if necessary!!! If not, gunicorn.conf.py
only needs to contain `from boostutils.configuration.gunicorndefaults import *`.

http://docs.gunicorn.org/en/stable/settings.html
"""

import sys
import threading
import traceback

# The Access log file to write to.
# "-" means stdout.
accesslog = "-"


# The socket to bind.
# A string of the form: HOST, HOST:PORT, unix:PATH, fd://FD. An IP is a valid HOST.
bind = "0.0.0.0:8000"


def worker_abort(worker):
    """
    Called when a worker received the SIGABRT signal. This call generally happens on timeout.
    """
    worker.log.info("worker received SIGABRT signal")
    worker.log.warning(_get_traceback())


def worker_int(worker):
    """
    Called just after a worker exited on SIGINT or SIGQUIT.
    """
    worker.log.info("worker received SIGINT or SIGQUIT signal")
    worker.log.info(_get_traceback())


def _get_traceback():
    """
    Gets traceback for all threads in the current process.

    Returns: str containing the traceback

    https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py
    https://github.com/benoitc/gunicorn/blob/master/LICENSE

    2009-2018 (c) Benoît Chesneau <benoitc@e-engura.org>
    2009-2015 (c) Paul J. Davis <paul.joseph.davis@gmail.com>

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following
    conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
    OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
    HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
    WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.
    """
    thread_names_by_id = {thread.ident: thread.name for thread in threading.enumerate()}
    code = []
    for thread_id, stack in sys._current_frames().items():
        code.append("\n# Thread: %s(%d)" % (thread_names_by_id.get(thread_id, ""), thread_id))
        for filename, line_num, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s' % (filename, line_num, name))
            if line:
                code.append("  %s" % (line.strip()))
    return "\n".join(code)
