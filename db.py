import aiosqlite


async def db_start():
    async with aiosqlite.connect('database.db') as db:
        await db.execute(
            'CREATE TABLE IF NOT EXISTS tasks (message_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, conditions TEXT,  PRIMARY KEY(message_id, chat_id))')
        await db.execute(
            'CREATE TABLE IF NOT EXISTS blacklist (user_if TEXT PRIMARY KEY, skip_count INTEGER NOT NULL)')
        await db.execute(
            'CREATE TABLE IF NOT EXISTS users (user_id INTEGER NOT NULL,message_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, username TEXT NOT NULL,  conditions TEXT, PRIMARY KEY(user_id, message_id, chat_id))')
        await db.commit()


async def add_task(message_id, chat_id, message_text):
    async with aiosqlite.connect('database.db') as db:
        await db.execute("""INSERT INTO tasks (message_id, chat_id, conditions) VALUES (?,?,?) """,
                         (message_id, chat_id, message_text))
        await db.commit()


async def sent_check(user_id, message_id, chat_id):
    async with aiosqlite.connect('database.db') as db:
        cursor = await db.execute("""SELECT * FROM users WHERE user_id = ? AND message_id = ? AND chat_id = ?""",
                                  (user_id, message_id, chat_id))
        return await cursor.fetchone()


async def insert_user(user_id, message_id, chat_id, username, message_text):
    async with aiosqlite.connect('database.db') as db:
        await db.execute(
            """INSERT INTO users (user_id, message_id, chat_id, username, conditions) VALUES (?,?,?,?,?)""",
            (user_id, message_id, chat_id, username, message_text))
        await db.commit()


async def get_task(chat_id, message_id):
    async with aiosqlite.connect('database.db') as db:
        cursor = await db.execute(
            """SELECT message_id, conditions FROM tasks WHERE chat_id = ? AND message_id =?""",
            (chat_id, message_id))
        return await cursor.fetchone()


async def get_users_list(chat_id, message_id):
    async with aiosqlite.connect('database.db') as db:
        cursor = await db.execute(
            """SELECT user_id FROM users WHERE chat_id = ? AND message_id =?""",
            (chat_id, message_id))
        return await cursor.fetchall()


async def blacklist_add(user_id):
    async with aiosqlite.connect('database.db') as db:
        cursor = await db.execute(
            """SELECT user_id, skip_count FROM blacklist WHERE user_id = ?""", (user_id))
        result = await cursor.fetchone()
        if result is not None:
            await db.execute("""UPDATE blacklist SET skip_count = ? WHERE user_id = ?""", (1, user_id))
        else:
            await db.execute("""INSERT INTO blacklist (user_id, skip_count) VALUES (?,?)""", (user_id, 1))
        await db.commit()


async def blacklist_update():
    async with aiosqlite.connect('database.db') as db:
        await db.execute(
            """DELETE FROM blacklist WHERE skip_count = 0""")
        await db.commit()
        await db.execute("""UPDATE blacklist SET skip_count = 0 WHERE skip_count = 1""")
        await db.commit()
