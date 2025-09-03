import logging
import sys
import traceback
from flask import Flask, request, render_template, send_file, jsonify
import os
from werkzeug.utils import secure_filename
import re
from audio_processor import AudioProcessor
from pydub import AudioSegment

# Configure logging to output to stderr
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Enable Flask debug mode
app = Flask(__name__)
app.debug = True

def log_error(*args):
    print(*args, file=sys.stderr, flush=True)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'processed'
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024 * 1024  # Increase to 256MB
ALLOWED_EXTENSIONS = {'wav', 'mp3'}

# Ensure upload and output directories exist
for directory in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
    try:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
    except Exception as e:
        logger.error(f"Failed to create directory {directory}: {str(e)}")
        raise

# Add error handler for all exceptions
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error("Uncaught exception: %s", str(e))
    logger.error(traceback.format_exc())
    return jsonify({
        "error": "Internal server error",
        "details": str(e)
    }), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_base_filename(filename):
    """Extract base filename without pt2 suffix"""
    return re.sub(r'_pt2(?=\.[^.]+$)', '', filename)

def find_matching_files(uploaded_files):
    """Group files that need to be processed together"""
    file_groups = {}

    for filename in uploaded_files:
        base_filename = get_base_filename(filename)
        if base_filename not in file_groups:
            file_groups[base_filename] = {'part1': None, 'part2': None}

        if '_pt2.' in filename:
            file_groups[base_filename]['part2'] = filename
        else:
            file_groups[base_filename]['part1'] = filename

    return file_groups

def convert_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3 using pydub"""
    audio = AudioSegment.from_wav(wav_path)
    audio.export(mp3_path, format='mp3', bitrate='320k')

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    # Save uploaded files
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            uploaded_files.append(filename)

    # Group files that need to be processed together
    file_groups = find_matching_files(uploaded_files)

    # Process each group
    processor = AudioProcessor()
    results = []

    for base_filename, group in file_groups.items():
        try:
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], group['part1'])
            base_output_name = os.path.splitext(base_filename)[0]
            wav_output = os.path.join(app.config['OUTPUT_FOLDER'], f"{base_output_name}_final.wav")
            mp3_output = os.path.join(app.config['OUTPUT_FOLDER'], f"{base_output_name}_final.mp3")

            if group['part2']:  # Need to splice
                second_file = os.path.join(app.config['UPLOAD_FOLDER'], group['part2'])
                success = processor.process_audio(
                    input_path=input_path,
                    second_file=second_file,
                    output_path=wav_output,
                    interactive_splice=False  # Automated processing
                )
            else:  # Single file processing
                success = processor.process_audio(
                    input_path=input_path,
                    output_path=wav_output
                )

            if success:
                # Convert to MP3
                convert_to_mp3(wav_output, mp3_output)
                results.append({
                    'filename': base_filename,
                    'status': 'success',
                    'outputs': {
                        'wav': f"{base_output_name}_final.wav",
                        'mp3': f"{base_output_name}_final.mp3"
                    }
                })
            else:
                results.append({
                    'filename': base_filename,
                    'status': 'error',
                    'error': 'Processing failed'
                })

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error processing {base_filename}: {error_details}")  # Server-side logging
            results.append({
                'filename': base_filename,
                'status': 'error',
                'error': f"Error: {str(e)}\n{error_details}"
            })

    # Cleanup uploaded files
    for filename in uploaded_files:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        except:
            pass

    return jsonify({
        'message': 'Processing complete',
        'results': results
    })

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(
        os.path.join(app.config['OUTPUT_FOLDER'], filename),
        as_attachment=True
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)