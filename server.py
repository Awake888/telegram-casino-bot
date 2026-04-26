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
        cursor.execute('INSERT INTO users VALUES (?, 15000, 0)', (user_id,))
        conn.commit()
        balance = 15000
    else:
        balance = row[0]
    conn.close()
    return web.json_response({'balance': balance})

async def play_roulette(request):
    data = await request.json()
    user_id, bet, b_type = data['user_id'], int(data['bet']), data['type']
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    bal = cursor.fetchone()[0]
    if bet > bal or bet <= 0: return web.json_response({'error': 'Мало монет'}, status=400)
    
    num = random.randint(0, 36)
    is_red = num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    win = bet * 2 if (b_type == 'red' and is_red and num != 0) or (b_type == 'black' and not is_red and num != 0) else 0
    
    cursor.execute('UPDATE users SET balance = balance - ? + ? WHERE id = ?', (bet, win, user_id))
    conn.commit()
    conn.close()
    return web.json_response({'number': num, 'win': win})

# BLACKJACK
def get_card(): return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
def calc(h):
    s = sum(h)
    if s > 21 and 11 in h: s -= 10
    return s

async def bj_start(request):
    data = await request.json()
    u, bet = data['user_id'], int(data['bet'])
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE id = ?', (u,))
    if cursor.fetchone()[0] < bet: return web.json_response({'error': 'Мало монет'}, status=400)
    active_games[u] = {'bet': bet, 'p': [get_card(), get_card()], 'd': [get_card()]}
    g = active_games[u]
    return web.json_response({'player_hand': g['p'], 'player_score': calc(g['p']), 'dealer_hand': g['d'], 'dealer_score': calc(g['d']), 'status': 'playing'})

async def bj_action(request):
    data = await request.json()
    u, act = data['user_id'], data['action']
    g = active_games.get(u)
    if not g: return web.json_response({'error': 'Ошибка'}, status=400)
    if act == 'hit':
        g['p'].append(get_card())
        if calc(g['p']) > 21: return await end_bj(u, 'lose', 'Перебор!')
    elif act == 'stand':
        while calc(g['d']) < 17: g['d'].append(get_card())
        p, d = calc(g['p']), calc(g['d'])
        if d > 21 or p > d: return await end_bj(u, 'win', 'Выиграл!')
        elif p < d: return await end_bj(u, 'lose', 'Проиграл!')
        else: return await end_bj(u, 'draw', 'Ничья!')
    return web.json_response({'player_hand': g['p'], 'player_score': calc(g['p']), 'dealer_hand': g['d'], 'dealer_score': calc(g['d']), 'status': 'playing'})

async def end_bj(u, res, msg):
    g = active_games.pop(u)
    win = g['bet']*2 if res == 'win' else (g['bet'] if res == 'draw' else 0)
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance - ? + ? WHERE id = ?', (g['bet'], win, u))
    conn.commit()
    conn.close()
    return web.json_response({'player_hand': g['p'], 'player_score': calc(g['p']), 'dealer_hand': g['d'], 'dealer_score': calc(g['d']), 'status': res, 'message': msg})

async def claim_bonus(request):
    data = await request.json()
    u = data['user_id']
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + 5000 WHERE id = ?', (u,))
    conn.commit()
    conn.close()
    return web.json_response({'message': 'Зачислено 5,000!'})

app = web.Application()
cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")})
app.router.add_get('/get_balance', get_balance)
app.router.add_post('/play_roulette', play_roulette)
app.router.add_post('/bonus', claim_bonus)
app.router.add_post('/bj_start', bj_start)
app.router.add_post('/bj_action', bj_action)
for r in list(app.router.routes()): cors.add(r)

if __name__ == '__main__':
    init_db()
    web.run_app(app, port=4040)
