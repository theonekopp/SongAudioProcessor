# Song Audio Processor

This is a Flask web application that processes audio files. It can perform operations like splicing two audio files together.

## Local Setup Instructions

### 1. Install System Dependencies

This project requires `ffmpeg` and `libsndfile` for audio processing. Please install them on your system using the appropriate package manager.

**For macOS (using Homebrew):**
```bash
brew install ffmpeg libsndfile
```

**For Debian/Ubuntu (using APT):**
```bash
sudo apt-get update
sudo apt-get install ffmpeg libsndfile1
```

**For Windows (using Chocolatey):**
```bash
choco install ffmpeg libsndfile
```
*Note: You may need to add ffmpeg to your system's PATH manually if the installer does not do so.*

### 2. Create a Python Virtual Environment

It is highly recommended to use a virtual environment to manage the project's dependencies.

```bash
# Navigate to the project directory
cd /mnt/c/Users/mdkop/App Projects/songaudioprocessor

# Create a virtual environment named 'venv'
python3 -m venv venv

# Activate the virtual environment
# On macOS and Linux:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate
```

### 3. Install Python Dependencies

With the virtual environment activated, install the required Python packages from the `requirements.txt` file.

```bash
pip install -r requirements.txt
```

### 4. Run the Application

Once the dependencies are installed, you can start the Flask development server.

```bash
python main.py
```

The application will be available at `http://127.0.0.1:8080` in your web browser.
