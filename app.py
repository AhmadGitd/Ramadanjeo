# -*- coding: utf-8 -*-
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO, emit, join_room
import json
import random
import string
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ramadan_secret_key'

# Render understøtter WebSockets direkte, så vi behøver ikke tvinge polling her
socketio = SocketIO(app, cors_allowed_origins="*")

# Vi gemmer spillet i RAM (hukommelsen) - det er lynhurtigt!
games = {}

def load_questions():
    with open('questions.json', 'r', encoding='utf-8') as f:
        return json.load(f)

questions = load_questions()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/host')
def host():
    return render_template('host.html')

@socketio.on('create_game')
def on_create_game():
    room = ''.join(random.choices(string.ascii_uppercase, k=4))
    games[room] = {
        'scores': {}, 
        'used_cards': [],
        'current_mode': 'barn',
        'current_card': None,
        'game_started': False
    }
    join_room(room)
    emit('game_created', {'room': room}, to=room)

@socketio.on('join_game')
def on_join_game(data):
    room = data['room'].upper()
    if room in games:
        join_room(room)
        emit('player_joined', to=room)
        emit('update_state', games[room], to=room)
        return True
    return False

@socketio.on('setup_game')
def handle_setup(data):
    room = data['room']
    if room in games:
        games[room]['scores'] = {chr(65+i): 0 for i in range(data['count'])}
        games[room]['game_started'] = True
        emit('update_state', games[room], to=room)
        emit('load_questions', questions, to=room)

@socketio.on('open_card')
def handle_open(data):
    room = data['room']
    if room in games:
        card = next((q for q in questions if q['id'] == data['id']), None)
        if card:
            games[room]['current_card'] = card
            emit('card_opened', card, to=room)

@socketio.on('give_points')
def handle_points(data):
    room = data['room']
    if room in games:
        games[room]['scores'][data['team']] += data['points']
        if games[room]['current_card']:
            games[room]['used_cards'].append(games[room]['current_card']['id'])
            games[room]['current_card'] = None
        emit('update_state', games[room], to=room)
        emit('close_modal', to=room)

@socketio.on('reveal_answer')
def handle_reveal(data):
    emit('answer_revealed', to=data['room'])

@socketio.on('close_without_points')
def handle_close(data):
    room = data['room']
    if room in games:
        if games[room]['current_card']:
            games[room]['used_cards'].append(games[room]['current_card']['id'])
            games[room]['current_card'] = None
        emit('update_state', games[room], to=room)
        emit('close_modal', to=room)

if __name__ == '__main__':
    # Render bruger port 10000 som standard, men Flask finder selv ud af det via Gunicorn
    socketio.run(app)


