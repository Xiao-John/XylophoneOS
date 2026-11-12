# SPDX-License-Identifier: Apache-2.0
"""Start and reap both processes required by the Interactium Qt platform."""
import re

from process_smoke import command


def start_graphics(guest, *, fault_present=False, check_display=False):
    begin = len(guest.output)
    result = command(guest, 'display-start' + (' fault-present' if fault_present else ''),
                     b'result=0')
    display = int(re.search(rb'\[display-start\] pid=(\d+)', result)[1])
    guest.expect(b'[display-service] ready', start=begin)
    if check_display:
        command(guest, 'exec gfxdemo check', b'checks=pass')
    begin = len(guest.output)
    result = command(guest, 'spawn interactiumd', b'[loader] started pid=')
    compositor = int(re.search(rb'\[loader\] started pid=(\d+)', result)[1])
    guest.expect(b'[interactium-service] ready', start=begin, timeout=120)
    return display, compositor


def stop_graphics(guest, display, compositor):
    command(guest, f'kill {compositor}', b'kill: accepted')
    command(guest, f'wait {compositor}', b'kind=killed')
    command(guest, 'exec gfxdemo stop', b'kind=exited code=0')
    command(guest, f'wait {display}', b'kind=exited code=0')


def reap_compositor(guest, compositor):
    result = command(guest, f'wait {compositor}', b'kind=exited')
    # Loss of Display is detected by either the input poll or the next present.
    assert re.search(rb'kind=exited code=(11|13)\b', result), result


def check_first_present_fault(output):
    assert b'[display-service] fault_after_present' in output, output
    status = re.search(rb'\[wait\] pid=\d+ kind=exited code=(\d+)\b', output)
    assert status is not None, output
    code = int(status[1])
    if code == 1:
        # The target newlib abort path ends in _exit(1), not Unix signal status.
        assert b'XOS QPA: Interactium create-window failed' in output, output
        return 'window_creation'
    assert code == 72, output
    assert (b'XOS QPA: Interactium frame commit failed' in output or
            b'XOS QPA: Interactium disconnected' in output), output
    return 'frame_or_input_disconnect'


def compare_composited_pixels(reference, scanout):
    assert reference.size == scanout.size == (800, 600)
    # The compositor owns this cursor; the exported QImage contains client pixels.
    for rectangle in ((0, 0, 800, 300), (0, 318, 800, 600),
                      (0, 300, 400, 318), (413, 300, 800, 318)):
        assert reference.crop(rectangle).tobytes() == scanout.crop(rectangle).tobytes(), rectangle
    assert scanout.getpixel((400, 300)) == (16, 24, 32)
    assert scanout.getpixel((401, 304)) == (245, 247, 250)
    assert scanout.getpixel((412, 317)) == (16, 24, 32)
