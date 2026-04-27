from aiohttp import web
import random
import sqlite3
import time
import aiohttp_cors

active_games = {}

def init_db():
    conn = sqlite3.connect('casino.db', timeout=10)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                     (id INTEGER PRIMARY KEY, balance INTEGER, last_bonus INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect('casino.db', timeout=10, check_same_thread=False)

def uid(v):
    try: return int(v)
    except: return None

# БАЛАНС
async def get_balance(request):
    user_id = uid(request.query.get('user_id'))
    if not user_id:
        return web.json_response({'error': 'no user_id'}, status=400)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute('INSERT INTO users (id,balance,last_bonus) VALUES (?,25000,0)', (user_id,))
        conn.commit(); balance = 25000
    else:
        balance = row[0]
    conn.close()
    return web.json_response({'balance': balance})

# БОНУС
BONUS_CD = 3600
BONUS_AMT = [500, 1000, 250, 5000, 100, 2000, 750, 3000]

async def claim_bonus(request):
    data = await request.json()
    user_id = uid(data.get('user_id'))
    if not user_id:
        return web.json_response({'error': 'no user_id'}, status=400)
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance,last_bonus FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute('INSERT INTO users (id,balance,last_bonus) VALUES (?,25000,0)', (user_id,))
        conn.commit(); row = (25000, 0)
    now = int(time.time()); last = row[1] or 0; diff = now - last
    if diff < BONUS_CD:
        remaining = BONUS_CD - diff; m,s = divmod(remaining,60)
        conn.close()
        return web.json_response({'error': f'Бонус доступен через {m}:{s:02d}'}, status=429)
    amount = random.choice(BONUS_AMT)
    sector_index = BONUS_AMT.index(amount)
    cur.execute('UPDATE users SET balance=balance+?,last_bonus=? WHERE id=?', (amount,now,user_id))
    conn.commit(); conn.close()
    return web.json_response({'message': f'🎉 Вы выиграли {amount} монет!', 'sector_index': sector_index, 'amount': amount})

# РУЛЕТКА
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

async def play_roulette(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); b_type = data.get('type')
    VALID_TYPES = ('red','black','green','even','odd')
    if not user_id or bet < 1 or b_type not in VALID_TYPES:
        return web.json_response({'error': 'Неверные данные'}, status=400)
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row: conn.close(); return web.json_response({'error': 'Пользователь не найден'}, status=404)
    if row[0] < bet: conn.close(); return web.json_response({'error': 'Недостаточно монет!'}, status=400)
    num = random.randint(0,36)
    is_red = num in RED_NUMS
    is_even = num != 0 and num % 2 == 0
    # Подсчёт выигрыша
    if num == 0:
        win = bet * 14 if b_type == 'green' else 0
    elif b_type == 'red' and is_red: win = bet * 2
    elif b_type == 'black' and not is_red: win = bet * 2
    elif b_type == 'even' and is_even: win = bet * 2
    elif b_type == 'odd' and not is_even: win = bet * 2
    else: win = 0
    cur.execute('UPDATE users SET balance=balance-?+? WHERE id=?', (bet,win,user_id))
    conn.commit(); conn.close()
    return web.json_response({'number': num, 'win': win})

# БЛЭКДЖЕК
def get_card(): return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
def calc(hand):
    s=sum(hand); a=hand.count(11)
    while s>21 and a: s-=10; a-=1
    return s

async def bj_start(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0))
    if not user_id or bet<1: return web.json_response({'error':'Неверные данные'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
    conn.commit();conn.close()
    p=[get_card(),get_card()]; d=[get_card(),get_card()]
    active_games[user_id]={'bet':bet,'p':p,'d':d}
    return web.json_response({'player_hand':p,'player_score':calc(p),'dealer_hand':[d[0]],'dealer_score':d[0],'status':'playing'})

async def bj_action(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); action=data.get('action')
    g=active_games.get(user_id)
    if not g: return web.json_response({'error':'Игра не найдена'},status=400)
    if action=='hit':
        g['p'].append(get_card())
        if calc(g['p'])>21: return await end_bj(user_id,'lose','💥 Перебор!')
    elif action=='stand':
        while calc(g['d'])<17: g['d'].append(get_card())
        ps,ds=calc(g['p']),calc(g['d'])
        if ds>21 or ps>ds: return await end_bj(user_id,'win','🏆 Ты выиграл!')
        elif ps<ds: return await end_bj(user_id,'lose','😔 Дилер выиграл.')
        else: return await end_bj(user_id,'draw','🤝 Ничья!')
    return web.json_response({'player_hand':g['p'],'player_score':calc(g['p']),'dealer_hand':[g['d'][0]],'dealer_score':g['d'][0],'status':'playing'})

async def end_bj(user_id, result, msg):
    g=active_games.pop(user_id); bet=g['bet']
    payout = bet*2 if result=='win' else (bet if result=='draw' else 0)
    if payout>0:
        conn=get_conn();cur=conn.cursor()
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(payout,user_id))
        conn.commit();conn.close()
    return web.json_response({'player_hand':g['p'],'player_score':calc(g['p']),'dealer_hand':g['d'],'dealer_score':calc(g['d']),'status':result,'message':msg})

# АВИАТОР — ставка
async def aviator_bet(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0))
    if not user_id or bet<1: return web.json_response({'error':'Неверные данные'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
    conn.commit();conn.close()
    return web.json_response({'ok':True})

# АВИАТОР — кэшаут
async def aviator_cashout(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); mul = float(data.get('multiplier',1.0))
    if not user_id or bet<1 or mul<1: return web.json_response({'error':'Неверные данные'},status=400)
    payout = int(bet * mul)
    conn=get_conn();cur=conn.cursor()
    cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(payout,user_id))
    conn.commit();conn.close()
    return web.json_response({'ok':True,'payout':payout})

# APP
app = web.Application()
cors = aiohttp_cors.setup(app, defaults={"*": aiohttp_cors.ResourceOptions(allow_credentials=True,expose_headers="*",allow_headers="*",allow_methods="*")})
app.router.add_get('/get_balance', get_balance)
app.router.add_post('/play_roulette', play_roulette)
app.router.add_post('/bonus', claim_bonus)
app.router.add_post('/bj_start', bj_start)
app.router.add_post('/bj_action', bj_action)
app.router.add_post('/play_aviator_bet', aviator_bet)
app.router.add_post('/play_aviator_cashout', aviator_cashout)
for route in list(app.router.routes()): cors.add(route)

if __name__ == '__main__':
    init_db()
    print("✅ Сервер запущен на порту 4040")
    web.run_app(app, port=4040)
