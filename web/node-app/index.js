const express = require('express');
const path = require('path');
const fs = require('fs');
const session = require('express-session');
const passport = require('passport');
const DiscordStrategy = require('passport-discord').Strategy;
const { Client, GatewayIntentBits } = require('discord.js');
const mongoose = require('mongoose');

const app = express();

// --- MongoDB 接続設定 ---
const MONGO_URI = process.env.MONGO_URI || 'mongodb://admin:password@zephyrus-mongodb-svc:27017/zephyrus?authSource=admin';
mongoose.connect(MONGO_URI).catch(err => console.error('MongoDB connection error:', err));

const StatsSchema = new mongoose.Schema({
    _id: String,
    data: Object,
    updatedAt: { type: Date, default: Date.now }
});
const Stats = mongoose.model('Stats', StatsSchema);

// --- 0. Botクライアントの設定 ---
const client = new Client({ intents: [GatewayIntentBits.Guilds] });
const BOT_TOKEN = process.env.TOKEN; 
client.login(BOT_TOKEN);

// --- 1. 基本設定 ---
app.use(session({
    secret: process.env.SESSION_SECRET || 'default-secret-key',
    resave: false,
    saveUninitialized: false
}));

app.use(passport.initialize());
app.use(passport.session());

// --- 2. Discord認証設定 ---
const CLIENT_ID = '1394981150178414632';
const CLIENT_SECRET = process.env.CLIENT_SECRET; 

passport.serializeUser((user, done) => done(null, user));
passport.deserializeUser((obj, done) => done(null, obj));

passport.use(new DiscordStrategy({
    clientID: CLIENT_ID,
    clientSecret: CLIENT_SECRET,
    callbackURL: 'https://zephyrus.uniproject.jp/auth/callback',
    scope: ['identify', 'guilds']
}, (accessToken, refreshToken, profile, done) => {
    return done(null, profile);
}));

// 管理者権限(0x8)を持っているか判定する関数
function isAdministrator(permissions) {
    return (BigInt(permissions) & BigInt(0x8)) === BigInt(0x8);
}

// --- 3. ルーティング ---

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, '../public_html/index.html'));
});

app.get('/auth/login', passport.authenticate('discord'));

app.get('/auth/logout', (req, res) => {
    req.logout((err) => {
        if (err) { return next(err); }
        res.redirect('/');
    });
});

app.get('/auth/callback', passport.authenticate('discord', {
    failureRedirect: '/' 
}), (req, res) => {
    res.redirect('/dashboard'); 
});

app.get('/dashboard', (req, res) => {
    if (!req.isAuthenticated()) return res.redirect('/auth/login');
    res.sendFile(path.join(__dirname, '../public_html/dashboard/index.html'));
});

// 🚀 修正：ログインユーザー情報API（Bot導入済み判定付き）
app.get('/api/user', (req, res) => {
    if (!req.isAuthenticated()) {
        return res.status(401).json({ error: "Not logged in" });
    }

    // ユーザーが所属する全サーバー情報を加工
    const guilds = req.user.guilds.map(guild => {
        // 1. ユーザーがそのサーバーで管理者権限を持っているか
        const isAdmin = isAdministrator(guild.permissions);
        
        // 2. Botがそのサーバーに導入されているか
        const botIn = client.guilds.cache.has(guild.id);

        return {
            ...guild,
            is_admin: isAdmin,
            bot_in: botIn
        };
    });

    // フロントエンドに返すデータを整形
    res.json({
        username: req.user.username,
        id: req.user.id,
        avatar: req.user.avatar,
        guilds: guilds // 加工後のサーバーリスト
    });
});

app.get('/api/stats', async (req, res) => {
    try {
        const stats = await Stats.findById('bot_stats');
        if (!stats) return res.status(404).json({ error: "Stats not found in DB" });
        res.json(stats.data);
    } catch (err) {
        res.status(500).json({ error: "Database error" });
    }
});

app.use(express.static(path.join(__dirname, '../public_html')));

const PORT = 3000;
app.listen(PORT, () => {
    console.log(`🚀 Dashboard server running on port ${PORT}`);
});
