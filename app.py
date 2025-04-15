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
from deep_translator import GoogleTranslator

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

app = Flask(__name__)
CORS(app)

app.config['UPLOAD_FOLDER'] = 'static/audio'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Setup
DATABASE_URL = "sqlite:///./app.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()), unique=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AudioFile(Base):
    __tablename__ = 'audio_files'
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, default=lambda: str(uuid.uuid4()), unique=True)
    filename = Column(String, unique=True, index=True)
    user_id = Column(String, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    type = Column(String, nullable=False)

    user = relationship("User")

Base.metadata.create_all(bind=engine)

# Fallback: female voice handled same as male (due to pyttsx3 not supported in Render)
def synthesize_female_voice(text, language):
    tts = gTTS(text, lang=language)
    audio_filename = f"{uuid.uuid4()}.mp3"
    audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
    tts.save(audio_path)
    return audio_filename

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    db = SessionLocal()
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        db.close()
        return jsonify({"message": "User already exists"}), 400

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    new_user = User(username=username, email=email, password=hashed_password.decode('utf-8'))
    db.add(new_user)
    db.commit()
    db.close()
    return jsonify({"message": "Registration successful", "user_id": new_user.id})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    db.close()

    if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        return jsonify({"message": "Login successful", "user_id": user.id})
    return jsonify({"message": "Invalid credentials"}), 401

@app.route('/convert_text', methods=['POST'])
def convert_text():
    data = request.json
    text = data.get('text')
    user_id = data.get('user_id')
    language = data.get('language', 'en')
    voice = data.get('voice', 'male').strip().lower()

    if not text or not user_id:
        return jsonify({"error": "Missing text or user_id"}), 400

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    translated_text = GoogleTranslator(source="auto", target=language).translate(text) if language != "en" else text

    audio_filename = synthesize_female_voice(translated_text, language)  # Both male/female use gTTS
    audio_file = AudioFile(filename=audio_filename, user_id=user.id, type="text")
    db.add(audio_file)
    db.commit()
    db.close()

    return jsonify({
        "message": "Text converted to audio successfully",
        "audio_path": f"/static/audio/{audio_filename}"
    })

@app.route('/convert_pdf', methods=['POST'])
def convert_pdf():
    file = request.files['file']
    user_id = request.form.get('user_id')
    language = request.form.get('language', 'en')
    voice = request.form.get('voice', 'male').strip().lower()

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    reader = PyPDF2.PdfReader(file)
    text = ''.join([page.extract_text() or '' for page in reader.pages])
    translated_text = GoogleTranslator(source="auto", target=language).translate(text) if language != "en" else text

    audio_filename = synthesize_female_voice(translated_text, language)
    audio_file = AudioFile(filename=audio_filename, user_id=user.id, type="pdf")
    db.add(audio_file)
    db.commit()
    db.close()

    return jsonify({
        "message": "PDF converted to audio successfully",
        "audio_path": f"/static/audio/{audio_filename}"
    })

@app.route('/convert_image', methods=['POST'])
def convert_image():
    file = request.files['file']
    user_id = request.form.get('user_id')
    language = request.form.get('language', 'en')
    voice = request.form.get('voice', 'male').strip().lower()

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    img = Image.open(file)
    text = pytesseract.image_to_string(img)
    translated_text = GoogleTranslator(source="auto", target=language).translate(text) if language != "en" else text

    audio_filename = synthesize_female_voice(translated_text, language)
    audio_file = AudioFile(filename=audio_filename, user_id=user.id, type="image")
    db.add(audio_file)
    db.commit()
    db.close()

    return jsonify({
        "message": "Image converted to audio successfully",
        "audio_path": f"/static/audio/{audio_filename}"
    })

@app.route('/delete_audio', methods=['DELETE'])
def delete_audio():
    data = request.json or {}
    audio_id = data.get('audio_id')
    user_id = data.get('user_id')

    if not audio_id or not user_id:
        return jsonify({"error": "Missing audio_id or user_id"}), 400

    db = SessionLocal()
    audio = db.query(AudioFile).filter(AudioFile.id == audio_id, AudioFile.user_id == user_id).first()
    if not audio:
        db.close()
        return jsonify({"error": "Audio file not found"}), 404

    path = os.path.join(app.config['UPLOAD_FOLDER'], audio.filename)
    if os.path.exists(path):
        os.remove(path)

    db.delete(audio)
    db.commit()
    db.close()

    return jsonify({"message": "Audio file deleted successfully"})

@app.route('/audio-history/<user_id>', methods=['GET'])
def audio_history(user_id):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    audios = db.query(AudioFile).filter(AudioFile.user_id == user.id).all()
    data = [{
        "id": a.id,
        "filename": a.filename,
        "created_at": a.created_at.isoformat(),
        "type": a.type
    } for a in audios]
    db.close()
    return jsonify(data)

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'audio'), filename)

@app.route('/download/audio/<filename>')
def download_audio(filename):
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'audio'),
        filename,
        as_attachment=True
    )

@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"error": "Oops! The resource you’re looking for was not found. Please check the URL or try again."}), 404

if __name__ == '__main__':
    app.run(debug=True)
