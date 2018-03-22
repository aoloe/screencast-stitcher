# WebM Screenscast Stitcher

Manage a screencast project and merge it's parts into a WebM file.

A project can contain:

- WebM (VP9) video files
- SVG slides (rendered for a given duration)
- SVG overlays (rendered for a given duration on top of a single WebM)

The project is defined through a yaml file.

The WebM and SVG files are managed through external tools:

- `ffmpeg`
- `imagemagick` (`convert`)

Warning: this is alpha quality software!  
Use it at your own peril and only on copies of your files.

## Features

- Stitching WebM files together.
- Adding SVG slides.
- Applying SVG overlays.
- Adding text overlays.
- The project file can be managed in a git repository.
- Optional caching of the temporary files.

## Limits

- No sound support (for now)
- No validation is done, that what you feed the program is correct (dimensions, file types, ...; for now)
- All resources (WebM, SVG, PNG) must have the same dimensions.
- All the text overlays have the same formatting and position

## Usage

### Process the project

![](demo/readme/assets/project.png)
![](demo/readme/assets/plus.png)
![](demo/readme/assets/cover.png)
![](demo/readme/assets/plus.png)
![](demo/readme/assets/track-01.gif)
![](demo/readme/assets/plus.png)
![](demo/readme/assets/subtitle.png)
![](demo/readme/assets/plus.png)
![](demo/readme/assets/closing.png)
![](demo/readme/assets/equal.png)


```sh
screencast-stitcher.py [-o output.webm] screencast.yaml
```

Create an `ouptput.webm` file according to the structure in `screencast.yaml`

Options:

- `-o`: the output file name (default is `output.webm`)

### Creating a project file

Create the scheleton for the project file:

```sh
screencast-stitcher.py -generate [-o screencast.yaml] first.webm
```

The file will contain:

- the width and height of the WebM file
- the entries for the first WebM and for the cover and closing slides.

```yaml
size:
  width: 1400
  height: 1400
tracks:
  - file: cover.svg
    duration: 4
  - file: first.webm
  - file: closing.svg
    duration: 4
```

### Creating a slide template

Create an empty SVG file, of the size of the webm file:

```sh
screencast-stitcher.py -svg [-o template.svg] first.webm
```

### Adding overlays

- as SVG with a transparent background
- as a one line text string

### Creating an overlay template

Create an SVG file, of the size of the WebM file and with the screenshot at a specific time

```sh
screencast-stitcher.py -svg-frame 0:02 [-o frame.svg] first.webm
```

### Caching the tracks

Merging the WebM files is very fast, but generating the WebM from the SVGs is not.

Enabling the cache will store in the cache directory the generated yaml files.

```sh
screencast-stitcher.py -cache screencast.yaml
```

Currently, you can only have one project per cache directory.


TODO: add an option in the project file for defining the cache directory


### Converting to VP9

Convert a VP8 encoded WebM to use VP9:

```sh
screencast-stitcher.py -to-vp9 [-o output.webm] track.webm
```

### Get informations about a WebM

Shows the encoding, width and height of a specific WebM file

```sh
screencast-stitcher.py -size track.webm
```
TODO: probably, change it to info and show the size + the codec of each of its tracks

## Dependencies

External tools:

- `ffmpeg` (for most of the hard work)
- `imagemagick` (for `convert`)
- `mkvtoolnix` (for `mkvmerge`)

Python libraries:

- python3-yaml

## Ideas and alternatives

- https://www.npmjs.com/package/video-stitch

## Todo

- if the font name is not a path, first look in the local folder, than in `~/.fonts`, `/usr/share/fonts/...` (or other def.
- `-svg-frame` does not seem to work on WebMs with drawtext overlays
- create demo / test files
- fade out the text and slides?
  - https://video.stackexchange.com/questions/23481/ffmpeg-drawtext-fade-out 
- check the dimensions of all svg and WebM files!
- check that all WebM have vp9
- check the total times when extracting frames or adding overlays
- can `mkvmerge` be replaced by `ffmpeg`?
- only overwrite a default filename if `-force` is set
- check if the tools like `-svg` should not read from the yaml
- add /document sound?
  - espeak ?
  - festival ?
    - Nick1 voice is not bad (http://www.cstr.ed.ac.uk/projects/festival/morevoices.html)... but it does not seem that one can download it.
- check that the projects accepts file names with spaces  
  if not look into this:

  ```py
	import shlex

	raw = 'mkvmerge -o output.webm -w /tmp/tmpgqjqu0jx.webm +01.webm +/tmp/tmp4uipiirx.webm'

	split = shlex.split(raw)
	print(split)

	and_back = ' '.join(shlex.quote(s) for s in split)
	print(and_back)

	print(and_back == raw)
  ```
