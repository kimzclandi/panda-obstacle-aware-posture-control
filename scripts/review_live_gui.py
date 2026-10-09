"""Linux X11 review of the native demo window, with automatic physical run/exit.

Only this process's newly created Bullet window is saved. Captures happen before
the reference clock starts and after the task ends, never during execution.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.project_runtime import prepare_study, require_preflight


def bullet_windows():
    result = subprocess.run(['xwininfo', '-root', '-tree'], check=True, text=True, capture_output=True)
    # Do not guess a platform-dependent Bullet title. X11 window managers may
    # add unnamed frame windows; compare newly created named client windows.
    return {match.group(1):match.group(2) for line in result.stdout.splitlines()
            if (match:=re.match(r'\s*(0x[0-9a-fA-F]+)\s+"([^"]+)"',line))}


def capture_window(window, destination):
    from PIL import ImageGrab
    info = subprocess.run(['xwininfo', '-id', window, '-stats'], check=True, text=True, capture_output=True).stdout
    values = {}
    for label in ('Absolute upper-left X', 'Absolute upper-left Y', 'Width', 'Height'):
        values[label] = int(re.search(re.escape(label)+r':\s*(-?\d+)', info).group(1))
    x,y = values['Absolute upper-left X'],values['Absolute upper-left Y']
    width,height = values['Width'],values['Height']
    # Pillow's X11 capture supports bbox; window= is only supported on Win/macOS.
    ImageGrab.grab(bbox=(x,y,x+width,y+height), xdisplay=os.environ['DISPLAY']).save(destination)
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controller',choices=['tracker','potential','ppo'],default='ppo')
    args=parser.parse_args()
    args.index=ROOT/'study_index.json'
    require_preflight(args.index,gui=True)
    args.index,_,args.freeze=prepare_study(args.index)
    args.scenario=None;args.seed=144;args.autostart=True;args.exit_after_run=True
    from panda_posture.artifacts import make_run,write_json
    from scripts.live_demo_runtime import LiveDemo,read_inputs
    scene,params,checkpoint=read_inputs(args)
    out=make_run('native_gui_review',{'scope':'Display inspection plus one fixed validation rollout',
                                     'scenario_id':scene['id'],'controller':args.controller})
    (ROOT.parent/'native_gui_review_latest.txt').write_text(str(out)+'\n')
    old_windows=bullet_windows()
    class ReviewDemo(LiveDemo):
        def close_task(self):
            if self.task is not None and self.started and self.task.done:
                time.sleep(.25)  # Completed episode; never pause an active clock.
                capture_window(window,out/'completed.png')
            super().close_task()
    app=None
    try:
        app=ReviewDemo(args,scene,params,checkpoint)
        time.sleep(.8)
        after=bullet_windows()
        windows=set(after)-set(old_windows)
        write_json(out/'new_window_names.json',{key:after[key] for key in windows})
        # Some window managers give the decoration frame the client's title.
        # WM_STATE belongs to the managed client, not its decoration frame.
        properties={key:subprocess.run(['xprop','-id',key,'WM_STATE'],check=True,
                                       text=True,capture_output=True).stdout for key in windows}
        write_json(out/'window_state_properties.json',properties)
        windows={key for key in windows if 'WM_STATE(WM_STATE)' in properties[key]}
        if len(windows)!=1:
            raise RuntimeError('Cannot identify exactly one new Bullet window; refusing screenshot')
        window=windows.pop()
        geometry=capture_window(window,out/'ready.png')
        app.run()
        write_json(out/'summary.json',dict(captured=True,native_gui=True,window_geometry=geometry,
                    rollout_output=str(app.out),scope='Screenshots require visual inspection; fixed validation only'))
        print(json.dumps({'output':str(out)}),flush=True)
    except Exception as exc:
        write_json(out/'failure.json',{'error':str(exc)})
        if app is not None:
            app.close_task()
        raise


if __name__=='__main__':
    main()
