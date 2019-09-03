# #######################################################################################################
#
# This script will keep a mp3 copy (right side) in sync with a flac + mp3 collection (left side)
# Intended use is keeping a copy of your collection on a space limited (mobile) device.
# files are evaluated by last modification time and tag comparison according to this table:
#
#        | left only | right only |       left newer          | right newer |
#        |           |            | tags same | tags not same |             |
#  --------------------------------------------------------------------------
#  flac  | encode    | delete     | encode    | tag copy      | nothing     |
#  --------------------------------------------------------------------------
#  mp3   | copy      | delete     | copy      | tag copy      | nothing     |
#  --------------------------------------------------------------------------
#  other | copy      | delete     |         copy              | copy        |
#  --------------------------------------------------------------------------
#
# Some notes:
# There must be no mp3 and flac files with the same name in one folder.
# The script writes id3v2.4 UTF-8 encoded tags
# Embedded album art is not handled

# Adjust the variables below to your situation
# note: Double up the backslashes in windows paths

path_left = "D:\\Example\\OfaWindowsPath"
path_right = "\\\\WindowsNetwork\\Example"
lame_prog = "D:\\Lame3.100_64\\lame.exe"
lame_quality = 'V2'
flac_prog = "D:\\flac-1.3.2-win\\win64\\flac.exe"

# Set silent to True if you want nothing on screen.
silent = False

# These dirs and their subdirs will be ignored. So if they are on the left side they will not copied to the right side.
# If they are on the right side they will not be deleted.

dirs_to_ignore = [
    'example-1',
    'example-2'
]

# Map vorbis (=FLAC) tag field names to id3 frames.
# For field names that are not listed below, the TXXX frame will be used.
#
# tracktotal and disctotal should not be added here. If present they are combined with tracknumber and discnumber
# into the TRCK and TPOS frames, but they must be added as TXXX frame first.
#
# For extra mappings you can use:
# https://en.wikipedia.org/wiki/ID3#ID3v2_frame_specification
# https://wiki.hydrogenaud.io/index.php?title=Tag_Mapping
# https://wiki.hydrogenaud.io/index.php?title=Foobar2000:ID3_Tag_Mapping
# https://help.mp3tag.de/main_tags.html

vorbis_to_id3_map = {
    'artist':       'TPE1',
    'title':        'TIT2',
    'album':        'TALB',
    'albumartist':  'TPE2',
    'tracknumber':  'TRCK',
    'discnumber':   'TPOS',
    'composer': 	'TCOM',
    'conductor':    'TPE3',
    'remixer':      'TPE4',
    'date':         'TDRC',
    'comment':      'COMM',
    'genre':        'TCON',
    'language':     'TLAN',
    'bpm':          'TBPM'
}

# These id3 frames are ignored by the program for comparison.
# The TSSE frame is for encoder settings and is added by LAME.

id3_frames_to_ignore = [
    'TSSE'
]
# Do not edit anything below unless you know what you're doing
# ####################################################################################

from os import scandir
import os.path
import shutil
import subprocess
from mutagen import flac, id3, mp3


def print_if_not_silent(text):
    if not silent:
        print(text)


def get_id3_frame(tag_name, tag_value):
    """
    :param tag_name: str.
    :param tag_value: str.
    :return: mutagen ID3 frame
    """
    if tag_name in vorbis_to_id3_map:
        frame_name = vorbis_to_id3_map[tag_name]
        assert frame_name in id3.Frames, f"'{frame_name}' in vorbis_to_id3_map is not a valid frame type"
        frame_type = id3.Frames[frame_name]

        return frame_type(encoding=3, text=tag_value)

    else:
        return id3.TXXX(encoding=3, desc=tag_name, text=tag_value)


def xx_total_correct(tag_thing):
    """
    id3 tags combine the 'track/disc-number' and 'track/disc-total' fields in one frame (e.g. 3/14).

    :param tag_thing: mutagen.id3.ID3 object (= mp3.MP3.tags) or flac_like dict
    :return: corrected tags
    """
    if type(tag_thing) == id3.ID3:

        if all(x in tag_thing for x in ('TXXX:tracktotal', 'TRCK')):
            track_numb = tag_thing['TRCK'].text[0]
            track_tot = tag_thing['TXXX:tracktotal'].text[0]
            tag_thing.add(id3.TRCK(encoding=3, text=f'{track_numb}/{track_tot}'))
            tag_thing.delall('TXXX:tracktotal')

        if all(x in tag_thing for x in('TXXX:disctotal', 'TPOS')):
            track_numb = tag_thing['TPOS'].text[0]
            track_tot = tag_thing['TXXX:disctotal'].text[0]
            tag_thing.add(id3.TPOS(encoding=3, text=f'{track_numb}/{track_tot}'))
            tag_thing.delall('TXXX:disctotal')
        
        return tag_thing
    
    if type(tag_thing) == dict:

        if 'tracknumber' in tag_thing and '/' in tag_thing['tracknumber'][0]:
            track_numb, track_tot = tag_thing['tracknumber'][0].split('/')
            tag_thing['tracknumber'] = [track_numb]
            tag_thing['tracktotal'] = [track_tot]

        if 'discnumber' in tag_thing and '/' in tag_thing['discnumber'][0]:
            disc_numb, track_tot = tag_thing['discnumber'][0].split('/')
            tag_thing['discnumber'] = [disc_numb]
            tag_thing['disctotal'] = [track_tot]

        return tag_thing

    else:
        raise Exception('What is this thing?')


def copy_tag_dict_to_mp3(mp3_thing, tag_dict):
    """
    :param tag_dict: flac_like dict {'tag_name': ['tag_value', ...]}
    :param mp3_thing: mutagen.mp3.MP3 instance
    """
    for t in tag_dict.items():
        frame_to_add = get_id3_frame(t[0], t[1])
        mp3_thing.tags.add(frame_to_add)
        
    mp3_thing.tags = xx_total_correct(mp3_thing.tags)
    mp3_thing.save()


def id3_tags_as_dict(id3_tags):
    """
    :param id3_tags: mutagen.id3.ID3 object (= mp3.MP3.tags)
    :return: flac_like dict {'tag_name': ['tag_value', ...]}
    """
    id3_to_vorbis_map = {v: k for k, v in vorbis_to_id3_map.items()}
    flac_like_dict = {}

    for t in id3_tags:
        frame_id = id3_tags[t].FrameID
        if frame_id in id3_to_vorbis_map:
            key = id3_to_vorbis_map[frame_id]

        elif frame_id in id3_frames_to_ignore:
            continue

        else:
            try:
                key = id3_tags[t].desc
            except AttributeError:
                print(f"Ignored {t} frame in {id3_tags['TPE1']} - {id3_tags['TIT2']}")
                continue

        try:
            val = [str(x) for x in id3_tags[t].text]
        except AttributeError:
            print(f"Ignored {t} frame in {id3_tags['TPE1']} - {id3_tags['TIT2']}")
            continue

        flac_like_dict[key] = val

    flac_like_dict = xx_total_correct(flac_like_dict)

    return flac_like_dict


def flac_to_mp3(input_path, output_path, tag_dict=None):
    """
    Converts flac to mp3 and copies tags.

    :param input_path: str.
    :param output_path: str.
    :param tag_dict: flac_like dict {'tag_name': ['tag_value', ...]}
    """
    flac_options = '-d -s --force-raw-format --endian=little --sign=signed -c'
    lame_options = '-r --quiet --add-id3v2 --noreplaygain'

    cp1 = subprocess.run(f'"{flac_prog}" {flac_options} "{input_path}"', capture_output=True)
    subprocess.run(f'"{lame_prog}" -{lame_quality} {lame_options} "-" "{output_path}"',
                   input=cp1.stdout, capture_output=False)

    mp3_thing = mp3.MP3(output_path)
    if not tag_dict:
        tag_dict = flac.FLAC(input_path).tags.as_dict()
    copy_tag_dict_to_mp3(mp3_thing, tag_dict)


def get_files_dirs(path, level=0):
    music_files = {}
    rest_files = {}
    dir_dict = {}
    with scandir(path) as scan:
        for entry in scan:
            if entry.is_dir():
                if entry.name in dirs_to_ignore:
                    continue
                dir_dict[entry.name] = level

                # let's get recursive
                sub_music, sub_rest, sub_dirs = get_files_dirs(entry.path, level=level + 1)
                sub_music = {os.path.join(entry.name, x): y for x, y in sub_music.items()}
                sub_rest = {os.path.join(entry.name, x): y for x, y in sub_rest.items()}
                sub_dirs = {os.path.join(entry.name, x): y for x, y in sub_dirs.items()}
                music_files.update(sub_music)
                rest_files.update(sub_rest)
                dir_dict.update(sub_dirs)
            if entry.is_file():
                last_mod = entry.stat().st_mtime
                no_ext, ext = os.path.splitext(entry.name)
                if ext.lower() in ('.flac', '.mp3'):
                    music_files[no_ext] = {'ext': ext, 'last_mod': last_mod}
                else:
                    rest_files[entry.name] = last_mod

    return music_files, rest_files, dir_dict


class CompResult:
    def __init__(self, left, right):

        self.base_path_left = left
        self.base_path_right = right

        self.music_left, self.rest_left, self.dirs_left = get_files_dirs(left)
        self.music_right, self.rest_right, self.dirs_right = get_files_dirs(right)

        self.dirs_to_copy = {k: v for k, v in self.dirs_left.items() if k not in self.dirs_right}
        self.dirs_to_delete = {k: v for k, v in self.dirs_right.items() if k not in self.dirs_left}

        self.rest_to_copy, self.rest_to_delete = self._compare_files()
        self.music_leftonly, self.music_changed,  self.music_to_delete = self._compare_music()

    def _compare_files(self):
        files_to_delete = self.rest_right.keys() - self.rest_left.keys()

        files_to_copy = []
        for x in self.rest_left:
            if x in self.rest_right:
                if self.rest_left[x] != self.rest_right[x]:
                    files_to_copy.append(x)
            else:
                files_to_copy.append(x)

        return files_to_copy, files_to_delete

    def _compare_music(self):
        music_to_delete = {k: v for k, v in self.music_right.items() if k not in self.music_left}

        music_leftonly = []
        music_changed = []
        for x in self.music_left:
            if x in self.music_right:
                if self.music_left[x]['last_mod'] > self.music_right[x]['last_mod']:
                    music_changed.append(x)
            else:
                music_leftonly.append(x)

        return music_leftonly, music_changed, music_to_delete

    def synchronise(self):
        self._copy_dirs()
        self._copy_files()
        self._copy_music_changed()
        self._copy_music_leftonly()
        self._remove_music()
        self._remove_files()
        self._remove_dirs()

    def _copy_music_changed(self):
        for x in self.music_changed:
            ext_left = self.music_left[x]['ext']
            full_path_left = os.path.join(self.base_path_left, f'{x}{ext_left}')
            if ext_left.lower() == '.flac':
                music_thing_left = flac.FLAC(full_path_left)
                tags_left = music_thing_left.tags.as_dict()
            elif ext_left.lower() == '.mp3':
                music_thing_left = mp3.MP3(full_path_left)
                tags_left = id3_tags_as_dict(music_thing_left.tags)
            else:
                raise Exception('What is this thing?')

            ext_right = self.music_right[x]['ext']
            assert ext_right == '.mp3', 'Target file is not .mp3'
            full_path_right = os.path.join(self.base_path_right, f'{x}{ext_right}')
            music_thing_right = mp3.MP3(full_path_right)
            tags_right = id3_tags_as_dict(music_thing_right.tags)

            if tags_left != tags_right:
                print_if_not_silent(f'copying tags {full_path_left}')
                copy_tag_dict_to_mp3(music_thing_right, tags_left)

            else:
                if ext_left.lower() == '.flac':
                    print_if_not_silent(f'encoding {full_path_left} to mp3')
                    flac_to_mp3(full_path_left, full_path_right, tag_dict=tags_left)
                else:
                    print_if_not_silent(f'copying {full_path_left} to right')
                    shutil.copy2(full_path_left, full_path_right)

    def _copy_music_leftonly(self):
        for x in self.music_leftonly:
            ext_left = self.music_left[x]['ext']
            full_path_left = os.path.join(self.base_path_left, f'{x}{ext_left}')
            destination_path = os.path.join(self.base_path_right, f'{x}.mp3')

            if ext_left.lower() == '.flac':
                print_if_not_silent(f'encoding {full_path_left}')
                flac_to_mp3(full_path_left, destination_path)

            elif ext_left.lower() == '.mp3':
                print_if_not_silent(f'copying {full_path_left}')
                shutil.copy2(full_path_left, destination_path)
            else:
                raise Exception(f'What is this thing? - {x}{ext_left}')

    def _remove_music(self):
        for k, v in self.music_to_delete.items():
            full_path = os.path.join(self.base_path_right, f"{k}{v['ext']}")
            print_if_not_silent(f'deleting {full_path}')
            os.remove(full_path)

    def _copy_files(self):
        for f in self.rest_to_copy:
            path_source = os.path.join(self.base_path_left, f)
            path_dest = os.path.join(self.base_path_right, f)
            print_if_not_silent(f'copying {path_source} to right')
            shutil.copy2(path_source, path_dest)

    def _remove_files(self):
        for f in self.rest_to_delete:
            path = os.path.join(self.base_path_right, f)
            print_if_not_silent(f'deleted {path}')
            os.remove(path)

    def _copy_dirs(self):
        for d in self.dirs_to_copy:
            path = os.path.join(self.base_path_right, d)
            try:
                os.makedirs(path)
            except FileExistsError:
                continue
            print_if_not_silent(f'created {path}')

    def _remove_dirs(self):
        dirs_aslist = [x for x, y in self.dirs_to_delete.items()]
        for d in reversed(dirs_aslist):
            path = os.path.join(self.base_path_right, d)
            print_if_not_silent(f'removed {path}')
            os.rmdir(path)


if __name__ == "__main__":
    comp = CompResult(path_left, path_right)
    comp.synchronise()
