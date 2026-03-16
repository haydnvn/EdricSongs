import re
import subprocess
import os
from pathlib import Path

# Configuration
TIMESTAMPS_FILE = "TimeStamps.txt"
INPUT_MP3 = "kinsley grey - WAKE ME UP MIX.mp3"
OUTPUT_DIR = "tracks"
ALBUM_COVER = "meme.png"
ALBUM_NAME = "kinsley grey - WAKE ME UP MIX"

def parse_timestamp(ts_str):
    """Convert timestamp string (M:SS, MM:SS, or H:MM:SS) to seconds."""
    # Remove any whitespace
    ts_str = ts_str.strip()

    # Split by colon
    parts = ts_str.split(':')

    if len(parts) == 2:
        # MM:SS or M:SS format
        minutes, seconds = map(int, parts)
        return minutes * 60 + seconds
    elif len(parts) == 3:
        # H:MM:SS format
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds

    return None

def sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames."""
    # Replace invalid characters with underscore
    invalid_chars = r'<>:"/\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    # Remove leading/trailing spaces and dots
    name = name.strip(' .')
    # Limit length to avoid path issues
    if len(name) > 200:
        name = name[:200]
    return name

def parse_timestamps_file(filepath):
    """Parse the timestamps file and return list of (start_seconds, track_name) tuples."""
    tracks = []

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue

            # New format: "Artist - Title start_timestamp - end_timestamp"
            # Example: "Slowboy x zaichkou888 x ivoxygen - astro 0:00 - 2:55"

            # Use regex to find timestamps at the end of the line
            # Pattern: anything, then timestamp, then " - ", then timestamp
            pattern = r'^(.+?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)$'
            match = re.match(pattern, line)

            if match:
                track_name = match.group(1).strip()
                start_timestamp_str = match.group(2).strip()
                # end_timestamp_str = match.group(3).strip()  # Not used currently, but available

                # Try to parse the start timestamp
                start_seconds = parse_timestamp(start_timestamp_str)
                if start_seconds is not None and track_name:
                    tracks.append((start_seconds, track_name))

    return tracks

def get_audio_duration(filepath):
    """Get the duration of an audio file in seconds using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def extract_track(input_file, output_file, start_time, duration, track_title, track_number):
    """Extract a track segment using ffmpeg with metadata and album cover."""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-t', str(duration),
        '-i', input_file,
        '-i', ALBUM_COVER,
        '-map', '0:a',
        '-map', '1:v',
        '-c:a', 'libmp3lame',
        '-q:a', '0',  # Highest quality VBR
        '-c:v', 'png',
        '-disposition:v', 'attached_pic',
        '-id3v2_version', '3',
        '-metadata:s:v', 'title=Album cover',
        '-metadata:s:v', 'comment=Cover (front)',
        '-metadata', f'title={track_title}',
        '-metadata', f'album={ALBUM_NAME}',
        '-metadata', f'track={track_number}',
        output_file
    ]
    subprocess.run(cmd, capture_output=True)

def add_metadata_to_existing_tracks():
    """Add metadata and album cover to existing tracks in the output folder."""
    import glob
    import tempfile
    import shutil

    mp3_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.mp3")))
    print(f"Found {len(mp3_files)} tracks to update")

    for filepath in mp3_files:
        filename = os.path.basename(filepath)
        # Extract track number and name from filename (e.g., "01 - Track Name.mp3")
        match = re.match(r'^(\d+)\s*-\s*(.+)\.mp3$', filename)
        if not match:
            print(f"Skipping {filename} - doesn't match expected format")
            continue

        track_number = int(match.group(1))
        track_name = match.group(2)

        print(f"Adding metadata to track {track_number}: {track_name[:50]}...")

        # Create temp file for output
        temp_fd, temp_path = tempfile.mkstemp(suffix='.mp3')
        os.close(temp_fd)

        cmd = [
            'ffmpeg', '-y',
            '-i', filepath,
            '-i', ALBUM_COVER,
            '-map', '0:a',
            '-map', '1:v',
            '-c:a', 'copy',
            '-c:v', 'copy',
            '-id3v2_version', '3',
            '-metadata:s:v', 'title=Album cover',
            '-metadata:s:v', 'comment=Cover (front)',
            '-metadata', f'title={track_name}',
            '-metadata', f'album={ALBUM_NAME}',
            '-metadata', f'track={track_number}',
            temp_path
        ]
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0:
            shutil.move(temp_path, filepath)
        else:
            os.remove(temp_path)
            print(f"  Error processing {filename}")

    print(f"\nDone! Updated metadata for tracks in '{OUTPUT_DIR}' folder")


def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Parse timestamps
    tracks = parse_timestamps_file(TIMESTAMPS_FILE)
    print(f"Found {len(tracks)} tracks to extract")

    # Get total duration of the input file
    total_duration = get_audio_duration(INPUT_MP3)
    print(f"Total duration: {total_duration:.2f} seconds")

    # Extract each track
    for i, (start_time, track_name) in enumerate(tracks):
        # Calculate duration (until next track or end of file)
        if i < len(tracks) - 1:
            duration = tracks[i + 1][0] - start_time
        else:
            duration = total_duration - start_time

        # Create output filename with track number
        safe_name = sanitize_filename(track_name)
        output_filename = f"{i + 1:02d} - {safe_name}.mp3"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        print(f"Extracting track {i + 1}/{len(tracks)}: {track_name[:50]}...")
        extract_track(INPUT_MP3, output_path, start_time, duration, track_name, i + 1)

    print(f"\nDone! Extracted {len(tracks)} tracks to '{OUTPUT_DIR}' folder")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--metadata-only":
        add_metadata_to_existing_tracks()
    else:
        main()
