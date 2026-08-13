from collections import deque
import queue
import threading


STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"


class RuntimeState:
    def __init__(self, settings):
        self.settings = settings
        self.samplerate = settings.samplerate
        self.input_samplerate = settings.samplerate
        self.input_blocksize = 1024
        self.mic_device = settings.mic_device
        self.pre_buffer = deque(maxlen=int(settings.samplerate * settings.pre_buffer_seconds / 512) + 2)
        self.audio_frames = []
        self.lock = threading.Lock()
        self.recording_state = STATE_IDLE
        self.recording_mode = "dictation"
        self.max_record_timer = None
        self.minimum_record_timer = None
        self.clipboard_snapshot = None
        self.is_pasting = False
        self.model = None
        self.client = None
        self.ai_cleanup = False
        self.stream = None
        self.last_audio_warning = None
        self.last_audio_callback_at = 0.0
        self.last_audio_rms = 0.0
        self.recording_started_at = 0.0
        self.recording_prebuffer_frames = 0
        self.ui_queue = queue.Queue()
