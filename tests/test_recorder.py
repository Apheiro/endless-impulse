"""GPU recorder argument validation and isolated session ownership."""
import datetime as dt
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'src/quickshell/scripts/videos/recorder.py'


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        env = patch.dict(os.environ, HOME=str(self.base), XDG_CONFIG_HOME=str(self.base/'config'), XDG_STATE_HOME=str(self.base/'state'), HYPRLAND_INSTANCE_SIGNATURE='test')
        env.start(); self.addCleanup(env.stop)
        spec = importlib.util.spec_from_file_location('recorder', SOURCE)
        self.r = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.r)
        self.config = self.r.settings()
        self.caps = dict(executable='/usr/bin/gpu-screen-recorder', flags=[f['flag'] for f in self.r.FIELDS] + ['-ipc','-o'], codecs=['h264','hevc'], installed=True)

    def args(self, config=None, context=None):
        return self.r.command(config or self.config, context or dict(target='fullscreen', monitor='DP-1'), self.caps, self.base/'out.mkv', self.base/'ipc.sock')

    def test_regular_recording_maps_settings_without_shell_expansion(self):
        config = dict(self.config, fps=144, bitrateMode='cbr', bitrateKbps=35000, plugins=['/tmp/a plugin.so'], saveScript='/tmp/save script')
        args, region = self.args(config)
        self.assertEqual(args[args.index('-w')+1], 'DP-1')
        self.assertEqual(args[args.index('-f')+1], '144')
        self.assertEqual(args[args.index('-q')+1], '35000')
        self.assertEqual(args[args.index('-p')+1], '/tmp/a plugin.so')
        self.assertIsNone(region)
        self.assertNotIn('-r', args)

    def test_repeated_audio_tracks_and_mixed_sources(self):
        config = dict(self.config, audioTracks=['default_output|default_input', 'app:firefox'])
        args, _ = self.args(config)
        self.assertEqual(args.count('-a'), 2)
        self.assertIn('default_output|default_input', args)
        self.assertIn('app:firefox', args)
        args, _ = self.args(dict(config, audioTracks=[]))
        self.assertNotIn('-a', args)

    def test_region_preserves_negative_desktop_coordinates(self):
        region = dict(x=-900, y=100, width=320, height=200)
        args, actual = self.args(context=dict(target='region', region=region))
        self.assertEqual(actual, region)
        self.assertEqual(args[args.index('-region')+1], '320x200+-900+100')
        self.assertEqual(args[args.index('-w')+1], 'region')

    def test_custom_capture_source_accepts_composition_and_portal(self):
        source = 'DP-1|/dev/video0;halign=end;width=30%;hflip=true'
        args, _ = self.args(dict(self.config, captureSource=source), dict(target='configured', monitor='DP-2'))
        self.assertEqual(args[args.index('-w')+1], source)
        args, _ = self.args(dict(self.config, captureSource='portal'), dict(target='configured'))
        self.assertIn('portal', args)

    def test_dynamic_paths_are_local_and_dates_include_weekday_and_time(self):
        config = dict(self.config, directoryPattern='%Y/%m/%A', filenamePattern='Capture_%d_%H-%M-%S')
        stamp = dt.datetime(2026,10,27,19,45,8)
        path = self.r.output_path(config, stamp)
        self.assertEqual(path, self.base/'Videos/2026/10/Tuesday/Capture_27_19-45-08.mp4')
        for changed in [dict(directoryPattern='../outside'), dict(directoryPattern='/outside'), dict(filenamePattern='../name'), dict(filenamePattern='%Q')]:
            with self.assertRaises(ValueError): self.r.validate(dict(config, **changed))
        self.assertFalse((self.base/'Videos').exists())

    def test_bad_numeric_settings_and_codec_container_combinations(self):
        for changed in [dict(fps=0),dict(fps=True),dict(fps=1.5),dict(keyint='nan'),dict(resolution='0x1080')]:
            with self.assertRaises(ValueError): self.r.validate(dict(self.config, **changed))
        for changed in [dict(codec='av1'), dict(container='webm',codec='h264'),dict(codec='hevc',encoder='cpu'),dict(container='mp3')]:
            with self.assertRaises(ValueError): self.args(dict(self.config, **changed))

    def test_replay_and_stream_options_do_not_leak_into_normal_recording(self):
        config = dict(self.config, mode='replay', replaySeconds=120, replayStorage='disk', parallelDirectory=str(self.base/'parallel'))
        args, _ = self.args(config)
        self.assertEqual(args[args.index('-r')+1], '120')
        self.assertIn('-ro', args)
        self.assertNotIn('-write-first-frame-ts', args)
        args, _ = self.args(dict(config, mode='record'))
        self.assertNotIn('-r', args)
        self.assertNotIn('-ro', args)

    def test_audio_only_omits_capture_and_video_flags(self):
        args, _ = self.args(dict(self.config, mode='audio', container='mp3', audioCodec='mp3'))
        self.assertNotIn('-w', args)
        self.assertNotIn('-k', args)
        self.assertNotIn('-f', args)
        self.assertIn('-a', args)

    def test_authentication_is_not_in_command_arguments(self):
        args, _ = self.args(dict(self.config, mode='stream', authToken='secret-password'))
        self.assertNotIn('-auth', args)
        self.assertNotIn('secret-password', args)

    def test_stale_session_and_reused_process_id_are_not_controllable(self):
        self.r.atomic(self.r.SESSION, dict(session='another', active=True, supervisor=os.getpid(), supervisorToken=self.r.process_token(os.getpid())))
        self.assertFalse(self.r.status()['active'])
        self.r.atomic(self.r.SESSION, dict(session='test', active=True, supervisor=os.getpid(), supervisorToken='wrong'))
        self.assertFalse(self.r.status()['active'])
        with patch.object(self.r.os, 'kill') as kill:
            self.r.control('stop')
            kill.assert_not_called()

    def test_preferences_are_private_and_legacy_save_directory_migrates_without_writes(self):
        self.r.atomic(self.r.CONFIG/'config.json', {'screenRecord':{'savePath':str(self.base/'Legacy videos')}})
        config = self.r.settings()
        self.assertEqual(config['saveDirectory'], str(self.base/'Legacy videos'))
        self.assertFalse(self.r.STORE.exists())
        self.r.atomic(self.r.STORE, self.r.validate(config))
        self.assertEqual(self.r.STORE.stat().st_mode & 0o777, 0o600)

    def test_help_with_nonzero_exit_is_still_parsed(self):
        from types import SimpleNamespace
        with patch.object(self.r.subprocess, 'run', return_value=SimpleNamespace(returncode=1,stdout='usage: gpu-screen-recorder [-w source] [-c mp4]',stderr='')):
            self.assertIn('-c', self.r.query('/usr/bin/gpu-screen-recorder', '--help'))

    def test_host_gpu_binary_does_not_inherit_nix_graphics_libraries(self):
        with patch.dict(os.environ, LD_LIBRARY_PATH='/nix/test', __EGL_VENDOR_LIBRARY_FILENAMES='/nix/mesa.json'):
            env=self.r.recorder_environment('/usr/bin/gpu-screen-recorder')
            self.assertNotIn('LD_LIBRARY_PATH',env)
            self.assertNotIn('__EGL_VENDOR_LIBRARY_FILENAMES',env)
            self.assertIn('LD_LIBRARY_PATH',self.r.recorder_environment('/nix/store/gsr/bin/gpu-screen-recorder'))

    def test_unknown_required_flags_fail_but_default_optional_flags_are_omitted(self):
        self.caps['flags'].remove('-low-power')
        self.args()
        with self.assertRaises(ValueError): self.args(dict(self.config, lowPower=True))
