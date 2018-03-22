#!/usr/bin/python3

import os
import sys
import datetime
import argparse
import yaml
import json
import subprocess
import tempfile
import base64
import hashlib
import shutil

svg_template = """<svg version="1.1"
    baseProfile="full"
    width="{width}" height="{height}"
    xmlns="http://www.w3.org/2000/svg">

    {content}
</svg>"""

svg_image_template = '<image id="image1JPEG" x="0" y="0" width="{width}" height="{height}" xlink:href="data:image/png;base64,{image}">'

debug = False

def main(argv):
    global debug

    args = get_args()

    debug = args.debug

    if args.info:
        info([f.name for f in args.file])
    elif args.svg:
        output_filename = 'template.svg' if args.output_file is None else args.output_file
        create_svg(args.file[0].name, output_filename)
    elif args.svg_frame:
        time = '{0:%M:%S}'.format(args.svg_frame)
        # TODO: add the timestamp to the default file name
        output_filename = 'frame.svg' if args.output_file is None else args.output_file
        create_svg_frame(args.file[0].name, time, output_filename)
    elif args.svg_to_webm:
        output_filename = 'output.webm' if args.output_file is None else args.output_file
        dimension, duration = args.svg_to_webm.split(':')
        dimension = dimension.split('x')
        create_webm_from_svg(args.file[0].name, dimension, duration, output_filename)
    elif args.to_vp9:
        output_filename = 'output.webm' if args.output_file is None else args.output_file
        webm_to_vp9(args.file[0].name, output_filename)
    elif args.generate:
        output_filename = 'screencast.yaml' if args.output_file is None else args.output_file
        generate_project_yaml(output_filename, get_webm_info(args.file[0].name), args.file[0].name)
    else:
        output_filename = 'output.webm' if args.output_file is None else args.output_file
        process(args.file[0], output_filename, args.cache)

def get_args():
    parser = argparse.ArgumentParser(description='Merge webm files according to a proeject file.')
    parser.add_argument('-info', action='store_true',
        help='return the encoding, width and height of webm file')
    parser.add_argument('-svg', action='store_true',
        help='create the svg template')
    parser.add_argument('-svg-frame', dest='svg_frame', action='store',
        type=lambda t: datetime.datetime.strptime(t, '%M:%S'),
        default=None,
        help='create an svg with the screenshot from a specific frame')
    parser.add_argument('-to-vp9', dest='to_vp9', action='store_true',
        help='convert a webm file to use the vp9 video codec')
    parser.add_argument('-svg-to-webm', dest='svg_to_webm', action='store',
        help='convert an svg to a webm file: -svg-to-webm "200x300:5"')
    parser.add_argument('-generate', dest='generate', action='store_true',
        help='generate the project yaml file')
    parser.add_argument('-cache', dest='cache', action='store_true',
        help='cache the processed temporary files')
    parser.add_argument('-cache-path', dest='cache_path', action='store',
        default=None,
        help='enable the cache in the given path')
    parser.add_argument('-o', dest='output_file', help='output file')
        # help='enable the cache in the given path')
    # parser.add_argument('-o', dest='output_file', metavar='out-file', type=argparse.FileType('w'),
        # help='output file')
    parser.add_argument('file', type=argparse.FileType('r'), nargs='+',
        default=None,
        help='file to be processed')
    parser.add_argument('-debug', action='store_true',
        help='output debug information')

    return parser.parse_args()

## high level functions called from main()

def process(filename_yaml, output_filename, cache):
    project = yaml.load(filename_yaml)
    # print(project)

    tracks_cache = Tracks_cache(cache, project)

    webm_tracks = []
    temp_trashcan = []

    for track in project['tracks']:
        file_basename, file_extension = os.path.splitext(track['file'])
        if file_extension == '.webm':
            filename = track['file']
        elif file_extension == '.svg':
            filename = tracks_cache.get(track)
            if not filename:
                filename_png = get_png_from_svg(track['file'], [project['size']['width'], project['size']['height']])
                filename = get_webm_from_png(filename_png, track['duration'])
                os.remove(filename_png)
                temp_trashcan.append(filename)
                tracks_cache.add(track, filename)
        elif file_extension == '.png':
            # TODO: add the caching
            filename = get_webm_from_png(filename, track['duration'])
            temp_trashcan.append(filename)

        if 'overlay' in track:
            filename_overlay = tracks_cache.get(track)
            if not filename_overlay:
                filename = get_webm_with_overlay(filename, track['overlay'], project)
                temp_trashcan.append(filename)

        if filename:
            webm_tracks.append(filename)

    if webm_tracks:
        generate_merged_webm(output_filename, webm_tracks)

    if temp_trashcan:
        for track in temp_trashcan:
            os.remove(track)

    tracks_cache.write()

def info(filenames):
    template = """- file: {}
      time: {}
      encoding: {}
      size: {} x {}"""
    for filename in filenames:
        info = get_webm_info(filename)
        print(template.format(
            filename,
            info['duration'],
            info['encoding'],
            info['width'],
            info['height']
        ))

def create_svg(filename, output_filename):
    info = get_webm_info(filename)
    # print(info)
    write_svg_file(output_filename, (info['width'], info['height']))

def create_svg_frame(filename, time, output_filename):
    # TODO: make sure that the timestamp is inside the webm length
    image = webm_extract_frame(filename, time)
    info = get_webm_info(filename)
    width, height = (info['width'], info['height'])
    write_svg_file(output_filename, [width, height], svg_image_template.format(width=width, height=height, image=image))

def create_webm_from_svg(filename, dimension, duration, output_filename):
    png_filename = get_png_from_svg(filename, dimension, transparent = True)
    shutil.copyfile(png_filename, 'tmp.png')
    webm_filename = get_webm_from_png(png_filename, duration)
    shutil.copyfile(webm_filename, output_filename)
    os.remove(png_filename)
    os.remove(webm_filename)

## functions doing the real work

# returns VP9 or VP8
def get_webm_codec(filename):
    data = subprocess.check_output(['mkvmerge', '--identification-format', 'json', '--identify', filename])
    data_json = json.loads(data)
    return data_json['tracks'][0]['codec'] # VP9 | VP8

def webm_extract_frame(filename, duration):
    # https://stackoverflow.com/questions/8577137/creating-a-tmp-file-in-python
    fd, path = tempfile.mkstemp(suffix='.png')
    os.remove(path)
    call_args = ['ffmpeg', '-i', filename, '-ss', duration, '-vframes', '1', path]
    subprocess.call(call_args)

    with open(path, "rb") as f:
        image = base64.b64encode(f.read()).decode('utf-8')
    f.close()
    os.close(fd)
    return image
 
def webm_to_vp9(filename, output):
    call_args = ['ffmpeg', '-i', filename, '-c:v', 'libvpx-vp9', output]
    subprocess.call(call_args)


def write_svg_file(filename, dimension, content = ''):
    svg = svg_template.format(width = dimension[0], height = dimension[1], content = content)
    with open(filename, 'w') as f:
        f.write(svg + '\n')
    f.close()

def generate_project_yaml(filename, info, reference_filename):
    project = {
        'size' : {
            'width': info['width'],
            'height': info['height']
        },
        'tracks' : [
            {'file': 'cover.svg', 'duration': 4},
            {'file': reference_filename},
            {'file': 'closing.svg', 'duration': 4}
        ]
    }
    # print(project)
    with open(filename, 'w') as f:
        yaml.dump(project, f, default_flow_style=False)
    f.close()

def get_png_from_svg(filename, dimension, transparent = False):
    fd, path = tempfile.mkstemp(suffix='.png')
    os.remove(path)
    args_transparent = ['-background', 'none'] if transparent else []
    call_args = ['convert', *args_transparent, '-density', str(300), '-resize', '{}x{}'.format(dimension[0], dimension[1]), filename, path]
    if debug:
        print(call_args)
    subprocess.call(call_args)
    os.close(fd)
    return path

def get_webm_from_png(filename, duration):
    fd, path = tempfile.mkstemp(suffix='.webm')
    os.remove(path)
    # eventually  '-vf scale=320:240' after yuv420p
    # libvpx-vp9 for vp9
    args_debug = ['-loglevel', 'panic'] if not debug else []
    call_args = ['ffmpeg', *args_debug, '-loop', str(1), '-i', filename, '-t', str(duration), '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', path]
    if debug:
        print(call_args)
    print(' '.join(call_args))
    subprocess.call(call_args)
    os.close(fd)
    return path

def get_webm_with_png_overlay(filename, filename_png, start, duration):
    fd, path = tempfile.mkstemp(suffix='.webm')
    os.remove(path)
    args_debug = ['-loglevel', 'panic'] if not debug else []
    call_args = ['ffmpeg', *args_debug, '-i', filename, '-i', filename_png, '-filter_complex', 'overlay=0:0:enable=\'between(t,{},{})\''.format(start, start + duration), path]
    if debug:
        print(call_args)
    print(' '.join(call_args))
    subprocess.call(call_args)
    os.close(fd)
    return path

def get_ffmpeg_text_overlay(text, start, duration, config):
    text = text.replace("'", r"'\\\''")
    drawtext = [
        "'between(t, {}, {})'".format(start, start + duration),
        'fontfile={}'.format(config['font']),
        "text='{}'".format(text),
        # 'text="{}"'.format(text),
        'fontcolor={}'.format(config['color']),
        'fontsize={}'.format(config['size']),
        'x={}'.format(config['x']),
        'y={}'.format(config['y'])
    ]
    return 'drawtext=enable='+':'.join(drawtext)

def get_webm_with_overlay(filename, overlays, project) :
    fd, path = tempfile.mkstemp(suffix='.webm')
    os.remove(path)
    text_overlay = []
    png_overlay = []
    for overlay in overlays :
        if 'file' in overlay:
            filename_png = get_png_from_svg(overlay['file'], [project['size']['width'], project['size']['height']], transparent=True)
            png_overlay.append([filename_png, overlay['start'], overlay['duration']])
        elif 'text' in overlay:
            text_overlay.append([overlay['text'], overlay['start'], overlay['duration']])
        pass
    overlay = []
    # print(text_overlay)
    first_i = 0
    if text_overlay :
        overlay.append('[{}:v]'.format(first_i) + ', '.join(get_ffmpeg_text_overlay(*t, project['text']) for t in text_overlay))
        first_i += 1
    # print(png_overlay)
    if png_overlay :
        overlay += ['[{}:v]'.format(first_i + i) + get_ffmpeg_png_overlay(t[1], t[2]) for i, t in enumerate(png_overlay)]

    args_debug = ['-loglevel', 'panic'] if not debug else []
    call_args = ['ffmpeg', *args_debug, '-i', filename]
    if png_overlay:
        for f in png_overlay:
            call_args += ['-i', f[0]]
    call_args += ['-filter_complex']
    call_between = []
    tag = ''
    for i, o in enumerate(overlay):
        item = tag + o
        tag = '[filter{}]'.format(i)
        item += tag
        call_between.append(item)

    call_args += ['; '.join(call_between), '-map', tag]
    call_args += [path]

    if debug:
        print(call_args)
    print(' '.join(call_args))
    subprocess.call(call_args)
    os.close(fd)
    # sys.exit()
    return path

def get_ffmpeg_png_overlay(start, duration):
    return "overlay=0:0:enable='between(t, {}, {})'".format(start, start + duration)

def generate_merged_webm(filename, tracks):
    # *(tracks[0], *('+' + t for t in tracks[1:]))
    args_tracks = ('{}{}'.format('+' if i > 0 else '', track) for i, track in enumerate(tracks))
    call_args = ['mkvmerge', '-o', filename, '-w', *(args_tracks)]
    print(' '.join(call_args))
    subprocess.call(call_args)


# first, process the "special" actions and exit

# how to require another argumets when one is set
# if ...
#      parser.error("-svg-frame requires -o")
#      sys.exit()

# if we got here, we're in the default mode and are processing the project

def get_webm_info(filename):
    # mkvmerge --identification-format json --identify 01.webm
    data = subprocess.check_output(['mkvmerge', '--identification-format', 'json', '--identify', filename])
    data_json = json.loads(data)
    # print(data_json)
    track_0 = data_json['tracks'][0]
    dimensions = track_0['properties']['pixel_dimensions'].split('x') # or display_dimensions
    duration = data_json['container']['properties']['duration']/1000000000
    duration = datetime.datetime.fromtimestamp(duration).strftime("%M:%S")
    return {'encoding': track_0['codec'], 'width': dimensions[0], 'height': dimensions[1], 'duration':duration}

class Tracks_cache():
    active = False
    tracks = {}
    matched = []
    cache_path = ''
    cache_file = ''
    def __init__(self, active, project):
        if not active:
            return
        self.active = active
        self.cache_path = project['cache_path'] if 'cache_path' in project else 'cache'
        self.cache_file = self.cache_path + '/cache.json'
        if not os.path.exists(self.cache_path):
            os.makedirs(self.cache_path)
        if os.path.isfile(self.cache_file):
            with open(self.cache_file, 'r') as f:
                self.tracks = json.load(f)

    def add(self, track, filename):
        if not self.active:
            return
        track_hash = self.get_hash(track)
        shutil.copyfile(filename, os.path.join(self.cache_path, track_hash))
        self.tracks[track_hash] = datetime.datetime.now().isoformat()
        self.matched.append(track_hash)
        # print(self.tracks)

    def get(self, track):
        if not self.active:
            return
        track_hash = self.get_hash(track)
        file_datetime = datetime.datetime.fromtimestamp(os.path.getmtime(track['file'])).isoformat()
        if track_hash in self.tracks and file_datetime < self.tracks[track_hash]:
            filename = os.path.join(self.cache_path, track_hash)
            if os.path.isfile(filename):
                self.matched.append(track_hash)
                return filename
        return

    def write(self):
        if not self.active:
            return
        # remove the tracks that are not in self.matched
        for track_hash in self.tracks.keys() - self.matched:
            os.remove(os.path.join(self.cache_path, track_hash))
            del self.tracks[track_hash]
        with open(self.cache_file, 'w') as f:
            json.dump(self.tracks, f)

    def get_hash(self, track):
        result = hashlib.md5(json.dumps(track, sort_keys=True).encode('utf-8')).digest()
        result = base64.urlsafe_b64encode(result).decode('utf-8')
        # print(result)
        return result

if __name__ == "__main__":
    main(sys.argv)
