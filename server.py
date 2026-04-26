from aiohttp import web
import random
import sqlite3
import aiohttp_cors
import time

active_games = {}

def init_db():
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, balance INTEGER, last_bonus INTEGER)')
    conn.commit()
    conn.close()

async def get_balance(request):
    user_id = request.query.get('user_id')
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    if not row:
        # УСТАНАВЛИВАЕМ 15,000 ПРИ ПЕРВОМ ВХОДЕ
        cursor.execute('INSERT INTO users VALUES (?, 15000, 0)', (user_id,))
        conn.commit()
        balance = 15000
    else:
        balance = row[0]
    conn.close()
    return web.json_response({'balance': balance})

async def play_roulette(request):
    data = await request.json()
    user_id, bet, bet_type = data['user_id'], int(data['bet']), data['type']
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    balance = cursor.fetchone()[0]
    if bet > balance or bet <= 0:
        return web.json_response({'error': 'Недостаточно монет'}, status=400)
    number = random.randint(0, 36)
    is_red = number in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    win = bet * 2 if (bet_type == 'red' and is_red and number != 0) or (bet_type == 'black' and not is_red and number != 0) else 0
    cursor.execute('UPDATE users SET balance = balance - ? + ? WHERE id = ?', (bet, win, user_id))
    conn.commit()
    conn.close()
    return web.json_response({'number': number, 'win': win})

def get_card():
    return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])

def calculate_score(hand):
    score = sum(hand)
    if score > 21 and 11 in hand: score -= 10
    return score

async def bj_start(request):
    data = await request.json()
    user_id, bet = data['user_id'], int(data['bet'])
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    balance = cursor.fetchone()[0]
    if bet > balance or bet <= 0: return web.json_response({'error': 'Мало монет'}, status=400)
    game = {'bet': bet, 'player_hand': [get_card(), get_card()], 'dealer_hand': [get_card()], 'status': 'playing'}
    active_games[user_id] = game
    return web.json_response({'player_hand': game['player_hand'], 'player_score': calculate_score(game['player_hand']), 'dealer_hand': game['dealer_hand'], 'dealer_score': calculate_score(game['dealer_hand']), 'status': 'playing'})

async def bj_action(request):
    data = await request.json()
    user_id, action = data['user_id'], data['action']
    game = active_games.get(user_id)
    if not game: return web.json_response({'error': 'Нет игры'}, status=400)
    if action == 'hit':
        game['player_hand'].append(get_card())
        if calculate_score(game['player_hand']) > 21: return await end_bj(user_id, 'lose', 'Перебор! Проигрыш.')
    elif action == 'stand':
        while calculate_score(game['dealer_hand']) < 17: game['dealer_hand'].append(get_card())
        p, d = calculate_score(game['player_hand']), calculate_score(game['dealer_hand'])
        if d > 21 or p > d: return await end_bj(user_id, 'win', 'Вы выиграли!')
        elif p < d: return await end_bj(user_id, 'lose', 'Дилер выиграл.')
        else: return await end_bj(user_id, 'draw', 'Ничья!')
    return web.json_response({'player_hand': game['player_hand'], 'player_score': calculate_score(game['player_hand']), 'dealer_hand': game['dealer_hand'], 'dealer_score': calculate_score(game['dealer_hand']), 'status': 'playing'})

async def end_bj(user_id, result, msg):
    game = active_games.pop(user_id)
    win = game['bet'] * 2 if result == 'win' else (game['bet'] if result == 'draw' else 0)
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance - ? + ? WHERE id = ?', (game['bet'], win, user_id))
    conn.commit()
    conn.close()
    return web.json_response({'player_hand': game['player_hand'], 'player_score': calculate_score(game['player_hand']), 'dealer_hand': game['dealer_hand'], 'dealer_score': calculate_score(game['dealer_hand']), 'status': result, 'message': msg})

async def claim_bonus(request):
    data = await request.json()
    user_id = data['user_id']
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + 5000 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return web.json_response({'message': 'Зачислено 5000 монет!'})

app = web.Application()
cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
app.router.add_get('/get_balance', get_balance)
app.router.add_post('/play_roulette', play_roulette)
app.router.add_post('/bonus', claim_bonus)
app.router.add_post('/bj_start', bj_start)
app.router.add_post('/bj_action', bj_action)
for route in list(app.router.routes()): cors.add(route)

if __name__ == '__main__':
    init_db()
    web.run_app(app, port=4040)
