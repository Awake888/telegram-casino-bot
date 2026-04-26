from aiohttp import web
import random
import sqlite3
import aiohttp_cors
import time

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
        cursor.execute('INSERT INTO users VALUES (?, 1000, 0)', (user_id,))
        conn.commit()
        balance = 1000
    else:
        balance = row[0]
    conn.close()
    return web.json_response({'balance': balance})

async def play_roulette(request):
    data = await request.json()
    user_id = data['user_id']
    bet = int(data['bet'])
    bet_type = data['type']
    
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    
    # Проверка баланса
    cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    current_balance = cursor.fetchone()[0]
    
    if bet > current_balance or bet <= 0:
        return web.json_response({'error': 'Недостаточно средств'}, status=400)

    number = random.randint(0, 36)
    red_nums = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
    is_red = number in red_nums
    
    win = 0
    if (bet_type == 'red' and is_red and number != 0) or \
       (bet_type == 'black' and not is_red and number != 0):
        win = bet * 2
    
    new_balance = current_balance - bet + win
    cursor.execute('UPDATE users SET balance = ? WHERE id = ?', (new_balance, user_id))
    conn.commit()
    conn.close()
    return web.json_response({'number': number, 'win': win})

async def claim_bonus(request):
    data = await request.json()
    user_id = data['user_id']
    now = int(time.time())
    
    conn = sqlite3.connect('casino.db')
    cursor = conn.cursor()
    cursor.execute('SELECT last_bonus FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    
    # Кулдаун 2 часа (7200 секунд)
    if row and (now - row[0]) < 7200:
        conn.close()
        return web.json_response({'message': 'Бонус еще не готов!'}, status=400)
        
    bonus_amount = 500
    cursor.execute('UPDATE users SET balance = balance + ?, last_bonus = ? WHERE id = ?', (bonus_amount, now, user_id))
    conn.commit()
    conn.close()
    return web.json_response({'message': f'Вы получили {bonus_amount} монет!'})

app = web.Application()
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers="*", allow_headers="*")
})

app.router.add_get('/get_balance', get_balance)
app.router.add_post('/play_roulette', play_roulette)
app.router.add_post('/bonus', claim_bonus)

for route in list(app.router.routes()):
    cors.add(route)

if __name__ == '__main__':
    init_db()
    print("Сервер запущен на порту 4040...")
    web.run_app(app, port=4040)