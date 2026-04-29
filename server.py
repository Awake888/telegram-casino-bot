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
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); b_type = data.get('type','')
    VALID_TYPES = ('red','black','green','even','odd','low','mid','high','low18','high18','row1','row2','row3')
    is_number_bet = b_type.startswith('number:')
    if not user_id or bet < 1 or (b_type not in VALID_TYPES and not is_number_bet):
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
    win = 0
    if is_number_bet:
        try:
            chosen = int(b_type.split(':')[1])
            if num == chosen: win = bet * 36
        except: pass
    elif num == 0:
        win = bet * 35 if b_type == 'green' else 0
    elif b_type == 'red' and is_red: win = bet * 2
    elif b_type == 'black' and not is_red: win = bet * 2
    elif b_type == 'even' and is_even: win = bet * 2
    elif b_type == 'odd' and not is_even: win = bet * 2
    elif b_type == 'low18' and 1 <= num <= 18: win = bet * 2
    elif b_type == 'high18' and 19 <= num <= 36: win = bet * 2
    elif b_type == 'low' and 1 <= num <= 12: win = bet * 3
    elif b_type == 'mid' and 13 <= num <= 24: win = bet * 3
    elif b_type == 'high' and 25 <= num <= 36: win = bet * 3
    elif b_type == 'row1' and num in {3,6,9,12,15,18,21,24,27,30,33,36}: win = bet * 3
    elif b_type == 'row2' and num in {2,5,8,11,14,17,20,23,26,29,32,35}: win = bet * 3
    elif b_type == 'row3' and num in {1,4,7,10,13,16,19,22,25,28,31,34}: win = bet * 3
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

# ОРЁЛ-РЕШКА
async def coin_flip(request):
    data = await request.json()
    user_id = uid(data.get('user_id'))
    bet = int(data.get('bet', 0))
    choice = data.get('choice', '')
    if not user_id or bet < 1 or choice not in ('heads', 'tails'):
        return web.json_response({'error': 'Неверные данные'}, status=400)
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row: conn.close(); return web.json_response({'error': 'Не найден'}, status=404)
    if row[0] < bet: conn.close(); return web.json_response({'error': 'Недостаточно монет!'}, status=400)
    result = random.choice(['heads', 'tails'])
    win = bet * 2 if result == choice else 0
    cur.execute('UPDATE users SET balance=balance-?+? WHERE id=?', (bet, win, user_id))
    conn.commit(); conn.close()
    return web.json_response({'result': result, 'win': win})

# КЕЙСЫ
CASES_FULL = {
    'starter': {'price':500, 'items':[
        {'v':-300,'ch':12,'e':'🪨','n':'Камень','r':'common'},
        {'v':-200,'ch':11,'e':'🍂','n':'Пыль','r':'common'},
        {'v':-150,'ch':10,'e':'🌫️','n':'Туман','r':'common'},
        {'v':-100,'ch':9, 'e':'🕸️','n':'Паутина','r':'common'},
        {'v':-50, 'ch':8, 'e':'🎃','n':'Тыква','r':'common'},
        {'v':-30, 'ch':6, 'e':'🥀','n':'Увядший','r':'common'},
        {'v':-20, 'ch':5, 'e':'🌑','n':'Пустота','r':'common'},
        {'v':50,  'ch':5, 'e':'🪙','n':'Монетка','r':'common'},
        {'v':100, 'ch':4, 'e':'💴','n':'Мелочь','r':'common'},
        {'v':200, 'ch':3, 'e':'🔑','n':'Ключик','r':'common'},
        {'v':300, 'ch':3, 'e':'🎫','n':'Билет','r':'common'},
        {'v':600, 'ch':5, 'e':'💰','n':'Кошелёк','r':'rare'},
        {'v':800, 'ch':4, 'e':'💵','n':'Купюра','r':'rare'},
        {'v':1200,'ch':4, 'e':'💳','n':'Карта','r':'rare'},
        {'v':2000,'ch':3, 'e':'💎','n':'Кристалл','r':'epic'},
        {'v':3000,'ch':2, 'e':'🔮','n':'Магия','r':'epic'},
        {'v':4000,'ch':1.5,'e':'🌟','n':'Звезда','r':'epic'},
        {'v':2500,'ch':2, 'e':'🏅','n':'Медаль','r':'epic'},
        {'v':7500,'ch':0.4,'e':'👑','n':'Корона','r':'legendary'},
        {'v':5000,'ch':0.6,'e':'⚡','n':'Молния','r':'epic'},
        {'v':15000,'ch':0.1,'e':'🏆','n':'Трофей','r':'legendary'},
    ]},
    'silver': {'price':1000, 'items':[
        {'v':-600,'ch':11,'e':'🪨','n':'Булыжник','r':'common'},
        {'v':-400,'ch':10,'e':'🍂','n':'Прах','r':'common'},
        {'v':-300,'ch':9, 'e':'🌫️','n':'Дым','r':'common'},
        {'v':-200,'ch':9, 'e':'🕸️','n':'Сеть','r':'common'},
        {'v':-100,'ch':8, 'e':'🎃','n':'Тыква гнилая','r':'common'},
        {'v':-60, 'ch':6, 'e':'🥀','n':'Сухоцвет','r':'common'},
        {'v':-40, 'ch':5, 'e':'🌑','n':'Тьма','r':'common'},
        {'v':100, 'ch':5, 'e':'🪙','n':'Серебрушка','r':'common'},
        {'v':250, 'ch':4, 'e':'💴','n':'Сторублёвка','r':'common'},
        {'v':500, 'ch':3, 'e':'🔑','n':'Серебряный ключ','r':'common'},
        {'v':700, 'ch':3, 'e':'🎫','n':'Талон','r':'common'},
        {'v':1300,'ch':5, 'e':'💰','n':'Портмоне','r':'rare'},
        {'v':1800,'ch':4, 'e':'💵','n':'Банкнота','r':'rare'},
        {'v':2500,'ch':3, 'e':'💳','n':'Золотая карта','r':'rare'},
        {'v':4000,'ch':3, 'e':'💎','n':'Алмаз','r':'epic'},
        {'v':6000,'ch':2, 'e':'🔮','n':'Оракул','r':'epic'},
        {'v':8000,'ch':1.5,'e':'🌟','n':'Суперзвезда','r':'epic'},
        {'v':5000,'ch':2, 'e':'🏅','n':'Серебряная медаль','r':'epic'},
        {'v':15000,'ch':0.4,'e':'👑','n':'Серебряная корона','r':'legendary'},
        {'v':10000,'ch':0.5,'e':'⚡','n':'Гром','r':'epic'},
        {'v':30000,'ch':0.1,'e':'🏆','n':'Серебряный кубок','r':'legendary'},
    ]},
    'gold': {'price':2500, 'items':[
        {'v':-1500,'ch':11,'e':'🪨','n':'Гравий','r':'common'},
        {'v':-1000,'ch':10,'e':'🍂','n':'Зола','r':'common'},
        {'v':-750, 'ch':9, 'e':'🌫️','n':'Смог','r':'common'},
        {'v':-500, 'ch':8, 'e':'🕸️','n':'Ловушка','r':'common'},
        {'v':-250, 'ch':8, 'e':'🎃','n':'Проклятие','r':'common'},
        {'v':-150, 'ch':6, 'e':'🥀','n':'Горечь','r':'common'},
        {'v':-100, 'ch':5, 'e':'🌑','n':'Чернота','r':'common'},
        {'v':300,  'ch':5, 'e':'🪙','n':'Золотник','r':'common'},
        {'v':700,  'ch':4, 'e':'💴','n':'Пятихатка','r':'common'},
        {'v':1500, 'ch':3, 'e':'🔑','n':'Золотой ключ','r':'common'},
        {'v':2000, 'ch':2, 'e':'🎫','n':'Ваучер','r':'common'},
        {'v':3500, 'ch':5, 'e':'💰','n':'Золотой сейф','r':'rare'},
        {'v':5000, 'ch':4, 'e':'💵','n':'Пачка купюр','r':'rare'},
        {'v':7500, 'ch':3, 'e':'💳','n':'Платиновая карта','r':'rare'},
        {'v':12000,'ch':3, 'e':'💎','n':'Бриллиант','r':'epic'},
        {'v':18000,'ch':2, 'e':'🔮','n':'Провидец','r':'epic'},
        {'v':25000,'ch':1, 'e':'🌟','n':'Галактика','r':'epic'},
        {'v':15000,'ch':1.5,'e':'🏅','n':'Золотая медаль','r':'epic'},
        {'v':40000,'ch':0.3,'e':'👑','n':'Золотая корона','r':'legendary'},
        {'v':30000,'ch':0.4,'e':'⚡','n':'Разряд','r':'epic'},
        {'v':75000,'ch':0.1,'e':'🏆','n':'Золотой кубок','r':'legendary'},
    ]},
    'diamond': {'price':5000, 'items':[
        {'v':-3000,'ch':11,'e':'🪨','n':'Уголь','r':'common'},
        {'v':-2000,'ch':10,'e':'🍂','n':'Осколки','r':'common'},
        {'v':-1500,'ch':9, 'e':'🌫️','n':'Туман войны','r':'common'},
        {'v':-1000,'ch':8, 'e':'🕸️','n':'Капкан','r':'common'},
        {'v':-500, 'ch':7, 'e':'🎃','n':'Злой рок','r':'common'},
        {'v':-300, 'ch':6, 'e':'🥀','n':'Разочарование','r':'common'},
        {'v':-200, 'ch':5, 'e':'🌑','n':'Провал','r':'common'},
        {'v':500,  'ch':5, 'e':'🪙','n':'Алмазник','r':'common'},
        {'v':1500, 'ch':4, 'e':'💴','n':'Тысячная','r':'common'},
        {'v':3000, 'ch':3, 'e':'🔑','n':'Алмазный ключ','r':'common'},
        {'v':4000, 'ch':2, 'e':'🎫','n':'Спецталон','r':'common'},
        {'v':7000, 'ch':5, 'e':'💰','n':'Бронированный сейф','r':'rare'},
        {'v':10000,'ch':4, 'e':'💵','n':'Кирпич денег','r':'rare'},
        {'v':15000,'ch':3, 'e':'💳','n':'Чёрная карта','r':'rare'},
        {'v':25000,'ch':3, 'e':'💎','n':'Идеальный алмаз','r':'epic'},
        {'v':40000,'ch':2, 'e':'🔮','n':'Всевидящий','r':'epic'},
        {'v':55000,'ch':1, 'e':'🌟','n':'Квазар','r':'epic'},
        {'v':35000,'ch':1.5,'e':'🏅','n':'Алмазная медаль','r':'epic'},
        {'v':90000,'ch':0.3,'e':'👑','n':'Алмазная корона','r':'legendary'},
        {'v':70000,'ch':0.4,'e':'⚡','n':'Шаровая молния','r':'epic'},
        {'v':150000,'ch':0.1,'e':'🏆','n':'Бриллиантовый кубок','r':'legendary'},
    ]},
    'vip': {'price':10000, 'items':[
        {'v':-6000,'ch':10,'e':'🪨','n':'Шлак','r':'common'},
        {'v':-4000,'ch':9, 'e':'🍂','n':'Хаос','r':'common'},
        {'v':-3000,'ch':9, 'e':'🌫️','n':'Пепел','r':'common'},
        {'v':-2000,'ch':8, 'e':'🕸️','n':'VIP-ловушка','r':'common'},
        {'v':-1000,'ch':7, 'e':'🎃','n':'Злой рок VIP','r':'common'},
        {'v':-600, 'ch':6, 'e':'🥀','n':'Фиаско','r':'common'},
        {'v':-400, 'ch':5, 'e':'🌑','n':'Чёрная дыра','r':'common'},
        {'v':1000, 'ch':4, 'e':'🪙','n':'VIP-монета','r':'common'},
        {'v':3000, 'ch':4, 'e':'💴','n':'Пятак','r':'common'},
        {'v':7000, 'ch':3, 'e':'🔑','n':'VIP-ключ','r':'common'},
        {'v':8000, 'ch':2, 'e':'🎫','n':'Пригласительный','r':'common'},
        {'v':15000,'ch':5, 'e':'💰','n':'VIP-сейф','r':'rare'},
        {'v':22000,'ch':4, 'e':'💵','n':'Чемодан наличных','r':'rare'},
        {'v':35000,'ch':3, 'e':'💳','n':'Карта мира','r':'rare'},
        {'v':60000,'ch':3, 'e':'💎','n':'VIP-алмаз','r':'epic'},
        {'v':90000,'ch':2, 'e':'🔮','n':'VIP-оракул','r':'epic'},
        {'v':130000,'ch':1,'e':'🌟','n':'Нейтронная звезда','r':'epic'},
        {'v':80000,'ch':1.5,'e':'🏅','n':'VIP-медаль','r':'epic'},
        {'v':200000,'ch':0.3,'e':'👑','n':'VIP-корона','r':'legendary'},
        {'v':150000,'ch':0.4,'e':'⚡','n':'Антиматерия','r':'epic'},
        {'v':400000,'ch':0.1,'e':'🏆','n':'Кубок чемпионов','r':'legendary'},
    ]},
    'legendary': {'price':25000, 'items':[
        {'v':-15000,'ch':10,'e':'🪨','n':'Метеорит','r':'common'},
        {'v':-10000,'ch':9, 'e':'🍂','n':'Судьба','r':'common'},
        {'v':-8000, 'ch':8, 'e':'🌫️','n':'Вакуум','r':'common'},
        {'v':-5000, 'ch':8, 'e':'🕸️','n':'Западня богов','r':'common'},
        {'v':-3000, 'ch':7, 'e':'🎃','n':'Проклятие богов','r':'common'},
        {'v':-1500, 'ch':6, 'e':'🥀','n':'Крах','r':'common'},
        {'v':-1000, 'ch':5, 'e':'🌑','n':'Горизонт событий','r':'common'},
        {'v':2500,  'ch':4, 'e':'🪙','n':'Легендарная монета','r':'common'},
        {'v':8000,  'ch':4, 'e':'💴','n':'Десятка тысяч','r':'common'},
        {'v':18000, 'ch':3, 'e':'🔑','n':'Мастер-ключ','r':'common'},
        {'v':20000, 'ch':2, 'e':'🎫','n':'VIP-пропуск','r':'common'},
        {'v':35000, 'ch':5, 'e':'💰','n':'Легендарный сейф','r':'rare'},
        {'v':55000, 'ch':4, 'e':'💵','n':'Состояние','r':'rare'},
        {'v':90000, 'ch':3, 'e':'💳','n':'Неограниченная карта','r':'rare'},
        {'v':150000,'ch':3, 'e':'💎','n':'Абсолютный алмаз','r':'epic'},
        {'v':225000,'ch':2, 'e':'🔮','n':'Пророчество','r':'epic'},
        {'v':350000,'ch':1, 'e':'🌟','n':'Пульсар','r':'epic'},
        {'v':200000,'ch':1.5,'e':'🏅','n':'Легендарная медаль','r':'epic'},
        {'v':500000,'ch':0.25,'e':'👑','n':'Корона богов','r':'legendary'},
        {'v':750000,'ch':0.15,'e':'⚡','n':'Сингулярность','r':'legendary'},
        {'v':1500000,'ch':0.1,'e':'🏆','n':'АБСОЛЮТ','r':'legendary'},
    ]},
}
# Для совместимости оставляем старый CASES_DATA
CASES_DATA = {k: {'price': v['price'], 'items': [(it['v'], it['ch']) for it in v['items']]} for k,v in CASES_FULL.items()}

def pick_prize_full(case_id):
    case = CASES_FULL.get(case_id)
    if not case: return None
    items = case['items']
    total = sum(it['ch'] for it in items)
    r = random.uniform(0, total)
    cum = 0
    for it in items:
        cum += it['ch']
        if r < cum:
            return it
    return items[-1]

async def open_case(request):
    data = await request.json()
    user_id = uid(data.get('user_id'))
    case_id = data.get('case_id','')
    count = max(1, min(int(data.get('count', 1)), 5))
    if not user_id or case_id not in CASES_FULL:
        return web.json_response({'error': 'Неверные данные'}, status=400)
    price = CASES_FULL[case_id]['price']
    total_cost = price * count
    conn = get_conn(); cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?', (user_id,))
    row = cur.fetchone()
    if not row: conn.close(); return web.json_response({'error': 'Не найден'}, status=404)
    if row[0] < total_cost:
        conn.close()
        return web.json_response({'error': f'Недостаточно монет! Нужно {total_cost:,}'}, status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?', (total_cost, user_id))
    conn.commit()
    prizes = []
    for _ in range(count):
        item = pick_prize_full(case_id)
        prize_value = item['v']
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?', (prize_value, user_id))
        conn.commit()
        prizes.append({
            'prize_value': prize_value,
            'name': item['n'],
            'emoji': item['e'],
            'rarity': item['r']
        })
    conn.close()
    return web.json_response({'ok': True, 'prizes': prizes})

# СЛОТЫ BONANZA
SLOT_SYMS = [
    {'e':'💎','n':'Diamond','w':50,'pays':{3:5,4:15,5:30,6:60}},
    {'e':'🔴','n':'Ruby',   'w':80,'pays':{3:3,4:8, 5:15,6:30}},
    {'e':'🔵','n':'Sapphire','w':90,'pays':{3:2,4:5, 5:10,6:20}},
    {'e':'🟡','n':'Gold',   'w':100,'pays':{3:2,4:4, 5:8, 6:15}},
    {'e':'🍇','n':'Grape',  'w':130,'pays':{3:1,4:3, 5:6, 6:12}},
    {'e':'🍋','n':'Lemon',  'w':160,'pays':{3:1,4:2, 5:4, 6:8}},
    {'e':'🍊','n':'Orange', 'w':180,'pays':{3:1,4:2, 5:3, 6:6}},
    {'e':'🍒','n':'Cherry', 'w':200,'pays':{3:1,4:1, 5:2, 6:4}},
    {'e':'🌸','n':'Scatter','w':30, 'pays':{}},  # scatter = фриспины
    {'e':'⭐','n':'Wild',   'w':40, 'pays':{}},  # wild
]
SCATTER_IDX=8; WILD_IDX=9

def slot_rand_sym():
    total=sum(s['w'] for s in SLOT_SYMS)
    r=random.uniform(0,total); cum=0
    for i,s in enumerate(SLOT_SYMS):
        cum+=s['w']
        if r<cum: return i
    return len(SLOT_SYMS)-1

async def slot_spin(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0))
    if not user_id or bet < 100:
        return web.json_response({'error':'Мин. ставка 100'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
    conn.commit()
    # Генерируем сетку 6×4
    grid=[[slot_rand_sym() for _ in range(4)] for _ in range(6)]
    # Верхний ряд — бонусные символы
    bonus_letters=['B','O','N','A','N','Z','A','💰']
    bonus_row=[random.choice(['B','O','N','A','💰','⭐','🔥']) for _ in range(4)]
    # Считаем выигрыши — каждый символ по всем колонкам
    sym_counts={}
    for col in range(6):
        col_syms=set(grid[col])
        for s in col_syms:
            if s!=SCATTER_IDX:
                sym_counts[s]=sym_counts.get(s,0)+1
    wins=[]; total_win=0; multiplier=1
    for sym,count in sym_counts.items():
        if count>=3:
            pay_table=SLOT_SYMS[sym]['pays']
            # Ближайший порог
            applicable=[k for k in pay_table.keys() if k<=count]
            if applicable:
                mult=pay_table[max(applicable)]
                payout=bet*mult
                # Собираем ячейки для подсветки
                cells=[]
                for col in range(6):
                    if sym in grid[col]:
                        cells.append(f"{col}_0")
                wins.append({'sym':sym,'count':count,'payout':payout,'mult':mult,'cells':cells})
                total_win+=payout
    # Scatter = фриспины
    scatter_count=sum(1 for col in range(6) for row in range(4) if grid[col][row]==SCATTER_IDX)
    freespins=0
    if scatter_count>=3: freespins=10+(scatter_count-3)*5
    if total_win>0:
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(total_win,user_id))
        conn.commit()
    conn.close()
    return web.json_response({'ok':True,'grid':grid,'bonus_row':bonus_row,'wins':wins,'total_win':total_win,'multiplier':multiplier,'freespins':freespins})

# СТАКАНЧИКИ
async def cups_guess(request):
    data = await request.json()
    user_id = uid(data.get('user_id')); bet = int(data.get('bet',0)); won = bool(data.get('won',False))
    if not user_id or bet<1:
        return web.json_response({'error':'Неверные данные'},status=400)
    conn=get_conn();cur=conn.cursor()
    cur.execute('SELECT balance FROM users WHERE id=?',(user_id,))
    row=cur.fetchone()
    if not row: conn.close(); return web.json_response({'error':'Не найден'},status=404)
    if not won and row[0]<bet: conn.close(); return web.json_response({'error':'Недостаточно монет!'},status=400)
    if won:
        win=bet*2
        cur.execute('UPDATE users SET balance=balance+? WHERE id=?',(win,user_id))
    else:
        cur.execute('UPDATE users SET balance=balance-? WHERE id=?',(bet,user_id))
        win=0
    conn.commit();conn.close()
    return web.json_response({'ok':True,'won':won,'win':win})

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
app.router.add_post('/coin_flip', coin_flip)
app.router.add_post('/slot_spin', slot_spin)
app.router.add_post('/cups_guess', cups_guess)
app.router.add_post('/open_case', open_case)
for route in list(app.router.routes()): cors.add(route)

if __name__ == '__main__':
    init_db()
    print("✅ Сервер запущен на порту 4040")
    web.run_app(app, port=4040)
