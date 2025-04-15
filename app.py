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
import asyncio
import edge_tts

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

# Full Edge-TTS Voice Map
VOICE_MAP = {
    "male": "en-US-GuyNeural",
    "female": "en-US-JennyNeural",
    "uk_male": "en-GB-RyanNeural",
    "uk_female": "en-GB-LibbyNeural",
    "indian_male": "en-IN-PrabhatNeural",
    "indian_female": "en-IN-NeerjaNeural",
    "spanish_male": "es-MX-JorgeNeural",
    "spanish_female": "es-MX-DaliaNeural",
    "german_male": "de-DE-ConradNeural",
    "german_female": "de-DE-KatjaNeural",
    "french_male": "fr-FR-HenriNeural",
    "french_female": "fr-FR-DeniseNeural"
}

async def synthesize_voice_edge(text, voice_id):
    filename = f"{uuid.uuid4()}.mp3"
    audio_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(audio_path)
    return filename

def synthesize_voice(text, language, voice):
    voice_id = VOICE_MAP.get(voice, VOICE_MAP["male"])
    return asyncio.run(synthesize_voice_edge(text, voice_id))

@app.route('/rename_audio', methods=['POST'])
def rename_audio():
    data = request.json
    audio_id = data.get("audio_id")
    new_filename = data.get("new_filename")

    if not audio_id or not new_filename:
        return jsonify({"error": "Missing audio_id or new_filename"}), 400

    db = SessionLocal()
    audio = db.query(AudioFile).filter(AudioFile.id == audio_id).first()
    if not audio:
        db.close()
        return jsonify({"error": "Audio file not found"}), 404

    old_path = os.path.join(app.config['UPLOAD_FOLDER'], audio.filename)
    new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)

    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        audio.filename = new_filename
        db.commit()

    db.close()
    return jsonify({"message": "Audio file renamed successfully"})

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
