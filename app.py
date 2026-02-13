from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ramadan_hemmelighed'
# cors_allowed_origins="*" er VIGTIGT for at det virker på nettet
# async_mode='threading' er VIGTIGT for cPanel/Nordicway
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- DATABASE (I HUKOMMELSEN) ---
# Her gemmer vi alle aktive spil.
# Format: { 'ABCD': { scores: {...}, current_card: ... } }
games = {}

def load_questions():
    with open('questions.json', 'r', encoding='utf-8') as f:
        return json.load(f)

questions = load_questions()

# Funktion til at lave en ny spil-tilstand
def create_new_game_state():
    return {
        'scores': {'A': 0, 'B': 0}, # Standard 2 hold, kan ændres
        'used_cards': [],
        'current_mode': 'barn',
        'current_card': None,
        'show_answer': False,
        'game_started': False
    }

# Generer en tilfældig 4-bogstavs kode (f.eks. "XYZA")
def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/host')
def host():
    return render_template('host.html')

# --- SOCKET EVENTS ---

@socketio.on('create_game')
def on_create_game():
    # Lav et unikt rum-ID
    room = generate_room_code()
    while room in games: # Sikr at den ikke findes
        room = generate_room_code()
    
    # Opret spillet i hukommelsen
    games[room] = create_new_game_state()
    
    # TV'et joiner dette rum
    join_room(room)
    
    # Send koden tilbage til TV'et så den kan vise det
    emit('game_created', {'room': room}, to=room)
    print(f"Spil oprettet i rum: {room}")

@socketio.on('join_game')
def on_join_game(data):
    room = data['room'].upper()
    
    if room in games:
        join_room(room)
        # VIGTIGT: Fortæl HELE rummet at der sker noget, og send nyeste data
        emit('player_joined', to=room) 
        emit('update_state', games[room], to=room)
        return True
    else:
        return False
# --- SPIL LOGIK (Nu med room-parameter!) ---

@socketio.on('setup_game')
def handle_setup(data):
    room = data['room']
    count = data['count']
    
    if room in games:
        game = games[room]
        # Nulstil og sæt hold
        game['scores'] = {}
        team_names = ['A', 'B', 'C', 'D']
        for i in range(count):
            game['scores'][team_names[i]] = 0
            
        game['game_started'] = True
        game['used_cards'] = []
        game['current_card'] = None
        
        # Send KUN til dette rum
        emit('update_state', game, to=room)
        emit('load_questions', questions, to=room)

@socketio.on('change_mode')
def handle_mode(data):
    room = data['room']
    if room in games:
        games[room]['current_mode'] = data['mode']
        emit('update_state', games[room], to=room)

@socketio.on('open_card')
def handle_open(data):
    room = data['room']
    card_id = data['id']
    
    if room in games:
        game = games[room]
        # Find kortet i den globale liste
        card = next((q for q in questions if q['id'] == card_id), None)
        
        if card and card_id not in game['used_cards']:
            game['current_card'] = card
            game['show_answer'] = False
            emit('card_opened', card, to=room)

@socketio.on('reveal_answer')
def handle_reveal(data):
    room = data['room']
    if room in games:
        games[room]['show_answer'] = True
        emit('answer_revealed', to=room)

@socketio.on('give_points')
def handle_points(data):
    room = data['room']
    team = data['team']
    points = data['points']
    
    if room in games:
        game = games[room]
        if team in game['scores']:
            game['scores'][team] += points
        
        # Luk kortet
        if game['current_card']:
            game['used_cards'].append(game['current_card']['id'])
            game['current_card'] = None
            
        emit('update_state', game, to=room)
        emit('close_modal', to=room)
        check_winner(room)

@socketio.on('deduct_points')
def handle_deduct(data):
    room = data['room']
    team = data['team']
    points = data['points']
    
    if room in games:
        games[room]['scores'][team] -= points
        emit('update_state', games[room], to=room)
        emit('play_sound', 'sound-wrong', to=room)

@socketio.on('close_without_points')
def handle_close(data):
    room = data['room']
    if room in games:
        game = games[room]
        if game['current_card']:
            game['used_cards'].append(game['current_card']['id'])
            game['current_card'] = None
        emit('update_state', game, to=room)
        emit('close_modal', to=room)
        check_winner(room)

@socketio.on('reset_game')
def handle_reset(data):
    room = data['room']
    if room in games:
        games[room] = create_new_game_state() # Nulstil totalt
        emit('update_state', games[room], to=room)
        emit('close_modal', to=room)

@socketio.on('show_rules')
def handle_rules(data):
    emit('show_rules', to=data['room'])

@socketio.on('force_close_modal')
def handle_force_close(data):
    emit('close_modal', to=data['room'])

def check_winner(room):
    game = games[room]
    # Logik for vinder (samme som før, bare med game objektet)
    mode_qs = [q for q in questions if q['niveau'] == game['current_mode']]
    
    used_count = 0
    for q in mode_qs:
        if q['id'] in game['used_cards']: used_count += 1
    
    if used_count >= len(mode_qs) and len(mode_qs) > 0:
        # Find vinder
        sorted_teams = sorted(game['scores'].items(), key=lambda x: x[1], reverse=True)
        winner_text = f"🏆 HOLD {sorted_teams[0][0]} VINDER! 🏆"
        if len(sorted_teams) > 1 and sorted_teams[0][1] == sorted_teams[1][1]:
            winner_text = "🤝 DET BLEV UAFGJORT!"
            
        emit('game_over', winner_text, to=room)

if __name__ == '__main__':
    # VIGTIGT: host='0.0.0.0' gør den synlig på nettet (hvis deployet)
    socketio.run(app, debug=True, host='0.0.0.0')