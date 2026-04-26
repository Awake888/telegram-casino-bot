from aiohttp import web
import random
import sqlite3
import aiohttp_cors

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
        # ПРИ ПЕРВОМ ВХОДЕ ВЫДАЕМ 15,000 МОНЕТ
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
    if bet > balance or bet <= 0: return web.json_response({'error': 'Мало монет!'}, status=400)
    
    number = random.randint(0, 36)
    is_red = number in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    win = bet * 2 if (bet_type == 'red' and is_red and number != 0) or (bet_type == 'black' and not is_red and number != 0) else 0
    
    cursor.execute('UPDATE users SET balance = balance - ? + ? WHERE id = ?', (bet, win, user_id))
    conn.commit()
    conn.close()
    return web.json_response({'number': str(number), 'win': win})

# ЛОГИКА 21 (BLACKJACK)
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
    if cursor.fetchone()[0] < bet: return web.json_response({'error': 'Мало монет!'}, status=400)
    
    active_games[user_id] = {'bet': bet, 'player': [get_card(), get_card()], 'dealer': [get_card()]}
    g = active_games[user_id]
    return web.json_response({'player_hand': g['player'], 'player_score': calculate_score(g['player']), 'dealer_hand': g['dealer'], 'dealer_score': calculate_score(g['dealer']), 'status': 'playing'})

async def bj_action(request):
    data = await request.json()
    u, action = data['user_id'], data['action']
    g = active_games.get(u)
    if not g: return web.json_response({'error': 'Игра не найдена'}, status=400)

    if action == 'hit':
        g['player'].append(get_card())
        if calculate_score(g['player']) > 21: return await end_bj(u, 'lose', 'Перебор! Вы проиграли.')
    elif action == 'stand':
        while calculate_score(g['dealer']) < 17: g['dealer'].append(get_card())
        p, d = calculate_score(g['player']), calculate_score(g['dealer'])
        if d > 21 or p > d: return await end_bj(u, 'win', 'Вы выиграли!')
        elif p < d: return await end_bj(u, 'lose', 'Дилер выиграл.')
        else: return await end_bj(u, 'draw', 'Ничья!')
    
    return web.json_response({'player_hand': g['player'], 'player_score': calculate_score(g['player']), 'dealer_hand': g['dealer'], 'dealer_score': calculate_score(g['dealer']), 'status': 'playing'})

async def end_bj(u, res, msg):
    g = active_games.pop(u)
    win = g['bet'] * 2 if res == 'win' else (g['bet'] if res == 'draw' else 0)
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance - ? + ? WHERE id = ?', (g['bet'], win, u))
    conn.commit()
    conn.close()
    return web.json_response({'player_hand': g['player'], 'player_score': calculate_score(g['player']), 'dealer_hand': g['dealer'], 'dealer_score': calculate_score(g['dealer']), 'status': res, 'message': msg})

async def claim_bonus(request):
    data = await request.json()
    u = data['user_id']
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + 5000 WHERE id = ?', (u,))
    conn.commit()
    conn.close()
    return web.json_response({'message': 'Зачислено 5,000 монет!'})

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
    print("Сервер запущен...")
    web.run_app(app, port=4040)
