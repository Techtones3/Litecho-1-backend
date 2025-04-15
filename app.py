from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from gtts import gTTS
import PyPDF2
from PIL import Image
import pytesseract
import os
import uuid
import datetime
import bcrypt
from deep_translator import GoogleTranslator  # Translation of input text

# Integration of pyttsx3 for an alternative female voice option
import pyttsx3

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Initialize the Flask application
app = Flask(__name__)
# Enable Cross-Origin Resource Sharing for frontend communication
CORS(app)

# Configure the directory for storing generated audio files
app.config['UPLOAD_FOLDER'] = 'static/audio'
# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- DATABASE SETUP ---
# Define the URL for the SQLite database
DATABASE_URL = "sqlite:///./app.db"
# Create a SQLAlchemy engine to interact with the database
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
# Create a session factory to generate database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Define the base for declarative models
Base = declarative_base()

# --- MODELS ---
# Define the User model for the 'users' table
class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()), unique=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Define the AudioFile model for the 'audio_files' table
class AudioFile(Base):
    __tablename__ = 'audio_files'
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, default=lambda: str(uuid.uuid4()), unique=True)
    filename = Column(String, unique=True, index=True)
    user_id = Column(String, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Specifies the type of content converted to audio (text, pdf, image)
    type = Column(String, nullable=False)

    # Establishes a relationship with the User model
    user = relationship("User")

# Create the database tables if they don't exist
Base.metadata.create_all(bind=engine)

# --- Helper: Synthesize audio using pyttsx3 for a female voice ---
def synthesize_female_voice(text, language):
    # Initialize the pyttsx3 engine
    engine = pyttsx3.init()
    # Get the available voices
    voices = engine.getProperty('voices')
    female_voice_id = None
    # Iterate through the voices to find a female one
    for v in voices:
        # Check if "female" is in the voice name or ID (OS dependent)
        if "female" in v.name.lower() or "female" in v.id.lower():
            female_voice_id = v.id
            break
    # Set the female voice if found
    if female_voice_id:
        engine.setProperty('voice', female_voice_id)
    # Generate a unique filename for the audio
    audio_filename = f"{uuid.uuid4()}.mp3"
    # Construct the full path to save the audio file
    audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
    # Save the synthesized speech to a file
    engine.save_to_file(text, audio_path)
    # Wait for the speech to finish
    engine.runAndWait()
    # Stop the engine
    engine.stop()
    return audio_filename

# --- ROUTES ---
# Route for user registration
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    # Access the database
    db = SessionLocal()
    # Check if a user with the given username or email already exists
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        db.close()
        return jsonify({"message": "User already exists"}), 400

    # Hash the user's password for security
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    # Create a new User object
    new_user = User(username=username, email=email, password=hashed_password.decode('utf-8'))
    # Add the new user to the database session
    db.add(new_user)
    # Commit the changes to the database
    db.commit()

    # Get the ID of the newly created user
    user_id = new_user.id
    # Close the database session
    db.close()
    return jsonify({"message": "Registration successful", "user_id": user_id})

# Route for user login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    # Access the database
    db = SessionLocal()
    # Retrieve the user with the given email
    user = db.query(User).filter(User.email == email).first()
    # Close the database session
    db.close()

    # Verify the password if the user exists
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        return jsonify({"message": "Login successful", "user_id": user.id})
    else:
        return jsonify({"message": "Invalid credentials"}), 401
    

# Route for converting text to audio
@app.route('/convert_text', methods=['POST'])
def convert_text():
    data = request.json
    text = data.get('text')
    user_id = data.get('user_id')
    language = data.get('language', 'en')
    # Get the requested voice (default to 'male' if not provided or empty)
    voice = data.get('voice', 'male')
    if not voice or not voice.strip():
        voice = "male"
    else:
        voice = voice.strip().lower()

    print("Voice option received in /convert_text:", voice)  # Logging the received voice option

    # Check if required data is missing
    if text is None or user_id is None:
        return jsonify({"error": "Missing 'text' or 'user_id' in request"}), 400

    # Access the database
    db = SessionLocal()
    # Retrieve the user from the database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    # Translate the text if the language is not English
    if language != "en":
        translated_text = GoogleTranslator(source="auto", target=language).translate(text)
    else:
        translated_text = text

    # Synthesize audio based on the selected voice
    if voice == "male":
        tts = gTTS(translated_text, lang=language)
        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        tts.save(audio_path)
    else:
        audio_filename = synthesize_female_voice(translated_text, language)

    # Create a new AudioFile record in the database
    audio_file = AudioFile(filename=audio_filename, user_id=user.id, type="text")
    db.add(audio_file)
    db.commit()
    db.close()

    return jsonify({
        "message": "Text converted to audio successfully",
        "audio_path": f"/static/audio/{audio_filename}"
    })

# Route for converting PDF to audio
@app.route('/convert_pdf', methods=['POST'])
def convert_pdf():
    file = request.files['file']
    user_id = request.form.get('user_id')
    language = request.form.get('language', 'en')
    voice = request.form.get('voice', 'male')
    if not voice or not voice.strip():
        voice = "male"
    else:
        voice = voice.strip().lower()

    print("Voice option received in /convert_pdf:", voice)  # Debug log

    # Access the database
    db = SessionLocal()
    # Retrieve the user from the database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    # Extract text content from the PDF file
    reader = PyPDF2.PdfReader(file)
    text = ''.join([page.extract_text() or '' for page in reader.pages])

    # Translate the extracted text if the language is not English
    if language != "en":
        translated_text = GoogleTranslator(source="auto", target=language).translate(text)
    else:
        translated_text = text

    # Synthesize audio based on the selected voice
    if voice == "male":
        tts = gTTS(translated_text, lang=language)
        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        tts.save(audio_path)
    else:
        audio_filename = synthesize_female_voice(translated_text, language)

    # Create a new AudioFile record in the database
    audio_file = AudioFile(filename=audio_filename, user_id=user.id, type="pdf")
    db.add(audio_file)
    db.commit()
    db.close()

    return jsonify({
        "message": "PDF converted to audio successfully",
        "audio_path": f"/static/audio/{audio_filename}"
    })

# Route for converting image to audio
@app.route('/convert_image', methods=['POST'])
def convert_image():
    file = request.files['file']
    user_id = request.form.get('user_id')
    language = request.form.get('language', 'en')
    voice = request.form.get('voice', 'male')
    if not voice or not voice.strip():
        voice = "male"
    else:
        voice = voice.strip().lower()

    print("Voice option received in /convert_image:", voice)  # Debug log

    # Access the database
    db = SessionLocal()
    # Retrieve the user from the database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    # Extract text from the image using OCR
    img = Image.open(file)
    text = pytesseract.image_to_string(img)

    # Translate the extracted text if the language is not English
    if language != "en":
        translated_text = GoogleTranslator(source="auto", target=language).translate(text)
    else:
        translated_text = text

    # Synthesize audio based on the selected voice
    if voice == "male":
        tts = gTTS(translated_text, lang=language)
        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        tts.save(audio_path)
    else:
        audio_filename = synthesize_female_voice(translated_text, language)

    # Create a new AudioFile record in the database
    audio_file = AudioFile(filename=audio_filename, user_id=user.id, type="image")
    db.add(audio_file)
    db.commit()
    db.close()

    return jsonify({
        "message": "Image converted to audio successfully",
        "audio_path": f"/static/audio/{audio_filename}"
    })

# Route for deleting an audio file
@app.route('/delete_audio', methods=['DELETE'])
def delete_audio():
    data = request.json or {}
    audio_id = data.get('audio_id')
    user_id = data.get('user_id')

    # Check if required data is missing
    if not audio_id or not user_id:
        return jsonify({"error": "Missing 'audio_id' or 'user_id' in request"}), 400

    # Access the database
    db = SessionLocal()
    # Retrieve the audio file associated with the user
    audio = db.query(AudioFile).filter(AudioFile.id == audio_id, AudioFile.user_id == user_id).first()
    if not audio:
        db.close()
        return jsonify({"error": "Audio file not found or not associated with this user"}), 404

    # Construct the full file path
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], audio.filename)
    # Delete the audio file from the file system if it exists
    if os.path.exists(file_path):
        os.remove(file_path)

    # Delete the audio file record from the database
    db.delete(audio)
    db.commit()
    db.close()

    return jsonify({"message": "Audio file deleted successfully"}), 200

# Route to get the audio history for a specific user
@app.route('/audio-history/<user_id>', methods=['GET'])
def audio_history(user_id):
    # Access the database
    db = SessionLocal()
    # Retrieve the user from the database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    # Retrieve all audio files associated with the user
    audios = db.query(AudioFile).filter(AudioFile.user_id == user.id).all()
    # Format the audio file data for the response
    audio_list = [
        {
            "id": audio.id,
            "filename": audio.filename,
            "created_at": audio.created_at.isoformat(),
            "type": audio.type
        }
        for audio in audios
    ]
    db.close()
    return jsonify(audio_list)

# Route to serve the static audio files
@app.route('/static/audio/<filename>')
def serve_audio(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'audio'), filename)

# Route to allow downloading of audio files
@app.route('/download/audio/<filename>')
def download_audio(filename):
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'audio'),
        filename,
        as_attachment=True # Set as_attachment to True for download
    )

# Run the Flask development server if the script is executed directly
if __name__ == '__main__':
    app.run(debug=True)