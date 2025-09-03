import soundfile as sf
import pyloudnorm as pyln
import numpy as np
from pydub import AudioSegment
import librosa
import os

class AudioProcessor:
    def __init__(self, target_lufs=-14.0, silence_duration=2.0, tolerance=0.1):
        """
        Initialize AudioProcessor with custom parameters
        target_lufs: Target loudness in LUFS (default: -14.0 for streaming)
        silence_duration: Seconds of silence to add at the end (default: 2.0)
        tolerance: Acceptable deviation from target LUFS (default: 0.1)
        """
        self.target_lufs = target_lufs
        self.silence_duration = silence_duration
        self.tolerance = tolerance

    def read_audio(self, file_path):
        """Read audio file and return data with sample rate."""
        return sf.read(file_path)

    def find_splice_points(self, audio1_path, audio2_path, num_candidates=5):
        """
        Find potential splice points between two audio files based on:
        - Beat alignment
        - Amplitude similarity
        - Spectral similarity
        Returns list of (time1, time2) pairs in seconds
        """
        # Load audio files using librosa for analysis
        audio1, sr1 = librosa.load(audio1_path)
        audio2, sr2 = librosa.load(audio2_path)

        # Get tempo and beat frames
        tempo1, beats1 = librosa.beat.beat_track(y=audio1, sr=sr1)
        tempo2, beats2 = librosa.beat.beat_track(y=audio2, sr=sr2)

        # Convert beat frames to times
        beat_times1 = librosa.frames_to_time(beats1, sr=sr1)
        beat_times2 = librosa.frames_to_time(beats2, sr=sr2)

        # Look at the last 10 seconds of first file and first 10 seconds of second file
        window = 10  # seconds
        candidates = []

        # Get beat positions in our windows of interest
        end_beats1 = beat_times1[beat_times1 > (len(audio1)/sr1 - window)]
        start_beats2 = beat_times2[beat_times2 < window]

        # For each potential splice point
        for t1 in end_beats1:
            for t2 in start_beats2:
                # Get short segments around these points
                seg1_start = int((t1 - 0.1) * sr1)
                seg1_end = int((t1 + 0.1) * sr1)
                seg2_start = int((t2 - 0.1) * sr2)
                seg2_end = int((t2 + 0.1) * sr2)

                if seg1_end >= len(audio1) or seg2_end >= len(audio2):
                    continue

                seg1 = audio1[seg1_start:seg1_end]
                seg2 = audio2[seg2_start:seg2_end]

                # Compare amplitude RMS
                rms1 = np.sqrt(np.mean(seg1**2))
                rms2 = np.sqrt(np.mean(seg2**2))
                amp_diff = abs(rms1 - rms2)

                # Compare spectral content
                spec1 = np.abs(librosa.stft(seg1))
                spec2 = np.abs(librosa.stft(seg2))
                spec_diff = np.mean(np.abs(spec1 - spec2))

                # Calculate overall similarity score
                similarity = 1 / (1 + amp_diff + spec_diff)

                candidates.append({
                    'time1': t1,
                    'time2': t2,
                    'similarity': similarity
                })

        # Sort by similarity and return top candidates
        candidates.sort(key=lambda x: x['similarity'], reverse=True)
        return candidates[:num_candidates]

    def concatenate_at_point(self, file1_path, file2_path, output_path, splice_point):
        """Concatenate two audio files at specific splice points with crossfade."""
        audio1 = AudioSegment.from_file(file1_path)
        audio2 = AudioSegment.from_file(file2_path)

        # Convert splice points to milliseconds
        t1_ms = int(splice_point['time1'] * 1000)
        t2_ms = int(splice_point['time2'] * 1000)

        # Split the audio files at the splice points
        first_part = audio1[:t1_ms]
        second_part = audio2[t2_ms:]

        # Apply crossfade
        crossfade_duration = 100  # milliseconds
        combined = first_part.append(second_part, crossfade=crossfade_duration)

        # Export
        combined.export(output_path, format="wav")
        return output_path

    def add_silence(self, audio_data, sample_rate):
        """Add silence at the end of the audio."""
        silence_samples = int(self.silence_duration * sample_rate)

        # Check if audio is stereo (2D) or mono (1D)
        if len(audio_data.shape) == 2:
            num_channels = audio_data.shape[1]
            silence = np.zeros((silence_samples, num_channels))
        else:
            silence = np.zeros(silence_samples)

        return np.concatenate([audio_data, silence])

    def measure_loudness(self, audio_data, sample_rate):
        """Measure integrated LUFS loudness of audio."""
        meter = pyln.Meter(sample_rate)
        return meter.integrated_loudness(audio_data)

    def adjust_loudness(self, audio_data, current_lufs, sample_rate, max_iterations=5):
        """
        Adjust audio to target LUFS using iterative adjustment for better precision.
        Uses multiple passes to achieve more accurate results.
        """
        adjusted_audio = audio_data
        meter = pyln.Meter(sample_rate)

        for i in range(max_iterations):
            # Measure current loudness
            current = meter.integrated_loudness(adjusted_audio)

            # Calculate required adjustment
            db_change = self.target_lufs - current

            # If we're close enough, stop iterating
            if abs(db_change) < self.tolerance:
                print(f"Target reached at iteration {i+1}")
                break

            # Apply adjustment with a damping factor for better convergence
            damping = 1.0 if i == 0 else 0.8  # Apply 80% of the calculated change after first iteration
            adjusted_audio = adjusted_audio * (10 ** ((db_change * damping) / 20))

            # Verify new loudness and print for debugging
            new_lufs = meter.integrated_loudness(adjusted_audio)
            print(f"Iteration {i+1}: LUFS = {new_lufs:.1f}")

        return adjusted_audio

    def process_audio(self, input_path, output_path, second_file=None, interactive_splice=False):
        """Main processing function that combines all steps."""
        try:
            # If we need to concatenate files
            if second_file:
                if interactive_splice:
                    # Find potential splice points
                    splice_candidates = self.find_splice_points(input_path, second_file)
                    splice_point = splice_candidates[0]  # Use best match for automated processing

                    # Concatenate at chosen point
                    self.concatenate_at_point(input_path, second_file, "temp_concatenated.wav", splice_point)
                    input_path = "temp_concatenated.wav"
                else:
                    # Simple concatenation
                    temp_path = "temp_concatenated.wav"
                    audio1 = AudioSegment.from_file(input_path)
                    audio2 = AudioSegment.from_file(second_file)
                    combined = audio1 + audio2
                    combined.export(temp_path, format="wav")
                    input_path = temp_path

            # Read the audio
            audio_data, sample_rate = self.read_audio(input_path)

            # Measure initial loudness
            initial_lufs = self.measure_loudness(audio_data, sample_rate)
            print(f"Initial loudness: {initial_lufs:.1f} LUFS")

            # First loudness adjustment
            if abs(initial_lufs - self.target_lufs) > 0.05:  # Stricter threshold
                print(f"Initial LUFS: {initial_lufs:.1f}")
                audio_data = self.adjust_loudness(audio_data, initial_lufs, sample_rate)
                intermediate_lufs = self.measure_loudness(audio_data, sample_rate)
                print(f"After first adjustment: {intermediate_lufs:.1f} LUFS")

            # Add silence at the end
            audio_data = self.add_silence(audio_data, sample_rate)

            # Second loudness adjustment after adding silence
            current_lufs = self.measure_loudness(audio_data, sample_rate)
            if abs(current_lufs - self.target_lufs) > 0.05:
                print(f"LUFS after silence: {current_lufs:.1f}")
                audio_data = self.adjust_loudness(audio_data, current_lufs, sample_rate)

            # Save the processed file
            sf.write(output_path, audio_data, sample_rate)

            # Verify final loudness
            final_lufs = self.measure_loudness(audio_data, sample_rate)
            print(f"Final loudness: {final_lufs:.1f} LUFS")

            # Cleanup
            if second_file and os.path.exists("temp_concatenated.wav"):
                os.remove("temp_concatenated.wav")

            return True

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error processing audio: {error_details}")
            raise Exception(f"Audio processing failed: {str(e)}\n{error_details}")