import os
import msvcrt
import shutil
import sys
import ctypes
from pathlib import Path

try:
	import yt_dlp
except ImportError:
	print("Missing dependency: yt-dlp")
	print("Install it with: pip install -r requirements.txt")
	sys.exit(1)


VIDEO_QUALITY_OPTIONS = [
	("Best available", "best[ext=mp4]/best"),
	("1080p or lower", "best[height<=1080][ext=mp4]/best[height<=1080]/best"),
	("720p or lower", "best[height<=720][ext=mp4]/best[height<=720]/best"),
	("480p or lower", "best[height<=480][ext=mp4]/best[height<=480]/best"),
	("Lowest quality (small file)", "worst"),
]

ANSI_RESET = "\033[0m"
ANSI_HIGHLIGHT = "\033[30;47m"


def enable_ansi_on_windows() -> bool:
	if os.name != "nt":
		return True

	kernel32 = ctypes.windll.kernel32
	handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
	if handle == 0:
		return False

	mode = ctypes.c_uint32()
	if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
		return False

	# ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004) enables ANSI styling on Windows terminals.
	new_mode = mode.value | 0x0004
	if kernel32.SetConsoleMode(handle, new_mode) == 0:
		return False

	return True


def clear_screen() -> None:
	os.system("cls" if os.name == "nt" else "clear")


def read_key() -> str:
	key = msvcrt.getch()

	# Handle arrow-key escape prefixes.
	if key in (b"\x00", b"\xe0"):
		arrow = msvcrt.getch()
		if arrow == b"H":
			return "up"
		if arrow == b"P":
			return "down"
		if arrow == b"K":
			return "left"
		if arrow == b"M":
			return "right"
		return "unknown"

	if key in (b"\r", b"\n"):
		return "enter"

	decoded = key.decode("utf-8", errors="ignore").lower()
	if decoded == "w":
		return "up"
	if decoded == "s":
		return "down"
	if decoded == "a":
		return "left"
	if decoded == "d":
		return "right"
	if decoded == "q":
		return "quit"

	return "unknown"


def render_menu_item(text: str, selected: bool, ansi_enabled: bool) -> str:
	if not selected:
		return f"  {text}"

	if ansi_enabled:
		return f"{ANSI_HIGHLIGHT}  {text}  {ANSI_RESET}"

	return f"[ {text} ]"


def menu_select(title: str, options: list[str], ansi_enabled: bool, allow_back: bool = False) -> int:
	index = 0

	while True:
		clear_screen()
		print("YouTube Downloader")
		print("=" * 50)
		print(title)
		print()

		for i, item in enumerate(options):
			print(render_menu_item(item, selected=(i == index), ansi_enabled=ansi_enabled))

		print()
		controls = "Use Arrow keys or W/S to move, Enter or D to select"
		if allow_back:
			controls += ", A to go back"
		print(controls)
		print("Press Q anytime to quit")
		print("Made by TechItAll")

		key = read_key()

		if key == "up":
			index = (index - 1) % len(options)
		elif key == "down":
			index = (index + 1) % len(options)
		elif key in ("enter", "right"):
			return index
		elif allow_back and key == "left":
			return -1
		elif key == "quit":
			raise KeyboardInterrupt


def ask_for_url() -> str:
	while True:
		clear_screen()
		print("YouTube Downloader")
		print("=" * 50)
		url = input("Paste a YouTube link and press Enter: ").strip()
		if url:
			return url
		print("Link cannot be empty. Press Enter to try again.")
		input()


def ffmpeg_is_available() -> bool:
	return shutil.which("ffmpeg") is not None


def pick_output_directory(initial_dir: Path) -> Path | None:
	try:
		import tkinter as tk
		from tkinter import filedialog
	except Exception:
		return None

	root = tk.Tk()
	root.withdraw()
	root.attributes("-topmost", True)

	selected = filedialog.askdirectory(
		title="Choose where to save downloaded files",
		initialdir=str(initial_dir.resolve()),
	)

	root.destroy()

	if not selected:
		return None

	return Path(selected)


def choose_output_dir(default_dir: Path, ansi_enabled: bool) -> Path | None:
	while True:
		choice = menu_select(
			"Choose save location",
			[
				f"Use default folder ({default_dir.resolve()})",
				"Pick destination in file explorer",
			],
			ansi_enabled=ansi_enabled,
			allow_back=True,
		)

		if choice == -1:
			return None

		if choice == 0:
			default_dir.mkdir(parents=True, exist_ok=True)
			return default_dir

		selected = pick_output_directory(default_dir)
		if selected is not None:
			selected.mkdir(parents=True, exist_ok=True)
			return selected

		clear_screen()
		print("No folder selected. Press Enter to choose again.")
		input()


def build_ydl_options(output_dir: Path, audio_only: bool, quality: str, has_ffmpeg: bool) -> dict:
	output_template = str(output_dir / "%(title)s [%(id)s].%(ext)s")

	options = {
		"outtmpl": output_template,
		"noprogress": False,
		"quiet": False,
		"restrictfilenames": True,
		"noplaylist": True,
	}

	if audio_only:
		if has_ffmpeg:
			options.update(
				{
					"format": "bestaudio/best",
					"postprocessors": [
						{
							"key": "FFmpegExtractAudio",
							"preferredcodec": "mp3",
							"preferredquality": "192",
						}
					],
				}
			)
		else:
			# Without FFmpeg, keep original audio format instead of converting to MP3.
			options["format"] = "bestaudio[ext=m4a]/bestaudio/best"
	else:
		options["format"] = quality

	return options


def run_download(url: str, audio_only: bool, quality: str, output_dir: Path, has_ffmpeg: bool) -> int:
	ydl_opts = build_ydl_options(output_dir, audio_only, quality, has_ffmpeg)

	if not has_ffmpeg:
		print("FFmpeg not found: using single-file formats that do not require merging.")
		if audio_only:
			print("Audio will be saved as available format (usually .m4a/.webm), not MP3.")

	try:
		with yt_dlp.YoutubeDL(ydl_opts) as ydl:
			ydl.download([url])
	except yt_dlp.utils.DownloadError as exc:
		print(f"Download failed: {exc}")
		return 1
	except Exception as exc:  # noqa: BLE001
		print(f"Unexpected error: {exc}")
		return 1

	print(f"Saved to: {output_dir.resolve()}")
	print("Done.")
	return 0


def main() -> int:
	default_output_dir = Path("downloads")
	default_output_dir.mkdir(parents=True, exist_ok=True)
	has_ffmpeg = ffmpeg_is_available()
	ansi_enabled = enable_ansi_on_windows()

	try:
		while True:
			url = ask_for_url()
			audio_only = False
			quality = "best"
			selection_label = "Audio only"

			mode_idx = menu_select(
				"Choose download type",
				["Video", "Audio only (MP3)"],
				ansi_enabled=ansi_enabled,
			)

			if mode_idx == 1:
				audio_only = True
				selection_label = "Audio only"
			else:
				quality_labels = [item[0] for item in VIDEO_QUALITY_OPTIONS]
				quality_idx = menu_select(
					"Choose video quality",
					quality_labels,
					ansi_enabled=ansi_enabled,
					allow_back=True,
				)

				if quality_idx == -1:
					continue

				quality = VIDEO_QUALITY_OPTIONS[quality_idx][1]
				selection_label = VIDEO_QUALITY_OPTIONS[quality_idx][0]

			output_dir = choose_output_dir(default_output_dir, ansi_enabled=ansi_enabled)
			if output_dir is None:
				continue

			clear_screen()
			print(f"Starting download ({selection_label})...")
			return run_download(
				url,
				audio_only=audio_only,
				quality=quality,
				output_dir=output_dir,
				has_ffmpeg=has_ffmpeg,
			)
	except KeyboardInterrupt:
		print("\nCancelled.")
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
