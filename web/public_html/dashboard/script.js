document.addEventListener('DOMContentLoaded', async () => {
    // プレビュー版のアラート
    alert("【お知らせ】\n現在ダッシュボードはプレビュー版です。\n設定の変更・保存はまだご利用いただけません。");

    try {
        // 1. ユーザー情報の取得（一回で済ませる）
        const response = await fetch('/api/user');
        if (!response.ok) return;

        const user = await response.json();
        console.log("ログインユーザー情報:", user);

        // 2. ヘッダーなどの共通UI反映
        updateUserUI(user);

        // 3. URLパラメータによる画面分岐
        const urlParams = new URLSearchParams(window.location.search);
        const serverId = urlParams.get('server');

        if (serverId) {
            // 個別設定画面を表示
            showManagePage(user, serverId);
        } else {
            // サーバー一覧画面を表示
            renderServerList(user);
        }

    } catch (err) {
        console.error("データの読み込みに失敗しました:", err);
    }
});

/**
 * ユーザーの基本情報（アバター、名前など）をUIに反映
 */
function updateUserUI(user) {
    const avatarUrl = user.avatar 
        ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`
        : "https://cdn.discordapp.com/embed/avatars/0.png";
    
    // 要素が存在する場合のみ代入
    const avatarImg = document.getElementById('user-avatar');
    const avatarLargeImg = document.getElementById('user-avatar-large');
    const nameDisplay = document.getElementById('user-name-display');

    if (avatarImg) avatarImg.src = avatarUrl;
    if (avatarLargeImg) avatarLargeImg.src = avatarUrl;
    if (nameDisplay) nameDisplay.innerText = user.username;

    // ドロップダウン制御
    const trigger = document.getElementById('user-menu-trigger');
    const dropdown = document.getElementById('user-dropdown');
    if (trigger && dropdown) {
        trigger.onclick = (e) => {
            dropdown.classList.toggle('show');
            e.stopPropagation();
        };
        window.addEventListener('click', () => dropdown.classList.remove('show'));
    }
}

/**
 * サーバー一覧カードの描画
 */
function renderServerList(user) {
    const serverListContainer = document.getElementById('server-list');
    if (!serverListContainer || !user.guilds) return;

    serverListContainer.innerHTML = ''; // 初期化

    // 管理者権限(0x8)を持つサーバーのみ表示
    const adminGuilds = user.guilds.filter(g => (g.permissions & 0x8) === 0x8);

    adminGuilds.forEach(guild => {
        const iconUrl = guild.icon 
            ? `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png`
            : "https://cdn.discordapp.com/embed/avatars/0.png";

        // URLの振り分け
        const inviteUrl = `https://discord.com/api/oauth2/authorize?client_id=1394981150178414632&permissions=4786570275581302&scope=bot%20applications.commands&guild_id=${guild.id}&disable_guild_select=true`;
        const manageUrl = `/dashboard?server=${guild.id}`;
        const targetUrl = guild.bot_in ? manageUrl : inviteUrl;

        const card = document.createElement('div');
        card.className = 'server-card';
        card.innerHTML = `
            <img src="${iconUrl}" class="server-icon" alt="${guild.name}">
            <p class="server-name">${guild.name}</p>
            <span class="status-badge">${guild.bot_in ? '設定する' : '導入する'}</span>
        `;

        card.onclick = () => {
            window.location.href = targetUrl;
        };

        serverListContainer.appendChild(card);
    });
}

/**
 * 個別設定画面の生成（タブ切り替えロジックを含む）
 */
function showManagePage(user, currentServerId) {
    const urlParams = new URLSearchParams(window.location.search);
    let currentTab = urlParams.get('tab') || 'info';

    const currentServer = user.guilds.find(g => g.id === currentServerId);
    if (!currentServer) return;

    const sidebarnav = document.querySelector('.sidebar nav');
    if (!sidebarnav) return;

    // サイドバーメニューのHTML構築
    sidebarnav.innerHTML = `
        <div class="server-switcher">
            <img src="https://cdn.discordapp.com/icons/${currentServer.id}/${currentServer.icon}.png" class="current-server-icon">
            <select onchange="location.href='/dashboard?server=' + this.value + '&tab=${currentTab}'">
                ${user.guilds.filter(g => (g.permissions & 0x8) === 0x8 && g.bot_in).map(g => `
                    <option value="${g.id}" ${g.id === currentServerId ? 'selected' : ''}>${g.name}</option>
                `).join('')}
            </select>
        </div>
        <ul class="manage-menu">
            ${renderMenuItem('info', 'サーバー情報', currentTab, currentServerId)}
            ${renderMenuItem('security', 'モデレーション', currentTab, currentServerId)}
            ${renderMenuItem('economy', '経済システム', currentTab, currentServerId)}
            ${renderMenuItem('tools', 'エンゲージメント', currentTab, currentServerId)}
            ${renderMenuItem('globalchat', 'グローバルチャット', currentTab, currentServerId)}
            ${renderMenuItem('admin', '管理・ログ', currentTab, currentServerId)}
            ${renderMenuItem('welcome', 'ようこそカード', currentTab, currentServerId)}
            <hr>
            <li><a href="/dashboard" style="color: #ff4757; text-decoration: none;">← 一覧に戻る</a></li>
        </ul>
    `;

    loadTabContent(currentServer, currentTab);
}

// ヘルパー: メニュー項目の生成
function renderMenuItem(id, label, currentTab, serverId) {
    return `<li class="menu-item ${currentTab === id ? 'active' : ''}" onclick="switchTab('${serverId}', '${id}')">${label}</li>`;
}

/**
 * タブ切り替え（リロードなし）
 */
async function switchTab(serverId, tabName) {
    const newUrl = `${window.location.pathname}?server=${serverId}&tab=${tabName}`;
    window.history.pushState({ path: newUrl }, '', newUrl);

    // activeクラスの付け替え
    document.querySelectorAll('.menu-item').forEach(item => {
        item.classList.remove('active');
        if(item.innerText === getTabDisplayName(tabName)) item.classList.add('active');
    });

    // ユーザー情報を再利用（または再取得）してコンテンツ更新
    const response = await fetch('/api/user');
    const user = await response.json();
    const server = user.guilds.find(g => g.id === serverId);
    loadTabContent(server, tabName);
}

function loadTabContent(server, tab) {
    const contentArea = document.querySelector('.content');
    if (!contentArea) return;

    switch (tab) {
        case 'info': renderServerInfo(server); break;
        case 'security': renderSecuritySettings(server); break;
        case 'economy': renderEconomySettings(server); break;
        // 他のタブもここに追加...
        default: contentArea.innerHTML = `<h2>${getTabDisplayName(tab)}</h2><p>現在準備中です。</p>`;
    }
}

function getTabDisplayName(tab) {
    const names = { 
        'info': 'サーバー情報', 
        'security': 'モデレーション', 
        'economy': '経済システム', 
        'tools': 'エンゲージメント', 
        'globalchat': 'グローバルチャット', 
        'admin': '管理・ログ', 
        'welcome': 'ようこそカード' 
    };
    return names[tab] || '';
}

// 以下、renderSecuritySettings などの各描画関数が続く...
// 個別設定画面の生成
// 個別設定画面の生成（メニュー項目を反映）
// 個別設定画面の生成（メニュー項目を反映）
function showManagePage(user, currentServerId) {
    const urlParams = new URLSearchParams(window.location.search);
    // URLにtabがあればそれを使い、なければデフォルトで 'info' を開く
    let currentTab = urlParams.get('tab') || 'info';

    const currentServer = user.guilds.find(g => g.id === currentServerId);
    if (!currentServer) return;

    // サイドバーの生成（メニュー項目にリンク形式ではなく、URL書き換え処理を付与）
    const sidebarnav = document.querySelector('.sidebar nav');
    sidebarnav.innerHTML = `
        <div class="server-switcher">
            <img src="https://cdn.discordapp.com/icons/${currentServer.id}/${currentServer.icon}.png" class="current-server-icon">
            <select onchange="location.href='/dashboard?server=' + this.value + '&tab=' + '${currentTab}'">
                ${user.guilds.filter(g => g.is_admin && g.bot_in).map(g => `<option value="${g.id}" ${g.id === currentServerId ? 'selected' : ''}>${g.name}</option>`).join('')}
            </select>
        </div>
        <ul class="manage-menu">
            <li class="menu-item ${currentTab === 'info' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'info')">サーバー情報</li>
            <li class="menu-item ${currentTab === 'security' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'security')">モデレーション</li>
            <li class="menu-item ${currentTab === 'economy' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'economy')">経済システム</li>
            <li class="menu-item ${currentTab === 'tools' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'tools')">エンゲージメント</li>
            <li class="menu-item ${currentTab === 'globalchat' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'globalchat')">グローバルチャット</li>
            <li class="menu-item ${currentTab === 'admin' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'admin')">管理・ログ</li>
            <li class="menu-item ${currentTab === 'welcome' ? 'active' : ''}" onclick="switchTab('${currentServerId}', 'welcome')">ようこそカード</li>
            <hr>
            <li><a href="/dashboard" style="color: #ff4757; text-decoration: none;">← 一覧に戻る</a></li>
        </ul>
    `;

    // 読み込み時のタブ表示
    loadTabContent(currentServer, currentTab);
}

// タブを切り替える関数（ページをリロードせずにURLだけ変えて中身を書き換える）
function switchTab(serverId, tabName) {
    // 1. URLを書き換える（履歴に残す）
    const newUrl = `${window.location.pathname}?server=${serverId}&tab=${tabName}`;
    window.history.pushState({ path: newUrl }, '', newUrl);

    // 2. メニューのactiveクラスを付け替え
    document.querySelectorAll('.menu-item').forEach(item => {
        item.classList.remove('active');
        if(item.textContent.includes(getTabDisplayName(tabName))) item.classList.add('active');
    });

    // 3. コンテンツの描画
    const userResponse = fetch('/api/user').then(res => res.json()).then(user => {
        const server = user.guilds.find(g => g.id === serverId);
        loadTabContent(server, tabName);
    });
}

// 実際に中身を書き換える分岐
function loadTabContent(server, tab) {
    if (tab === 'info') renderServerInfo(server);
    else if (tab === 'security') renderSecuritySettings(server);
    else if (tab === 'economy') renderEconomySettings(server);
    // ...他のタブも同様に
}

// タブ名から表示名を取得（activeクラス付け替え用ヘルパー）
function getTabDisplayName(tab) {
    const names = { 'info': 'サーバー情報', 'security': 'モデレーション', 'economy': '経済システム', 'tools': 'エンゲージメント', 'globalchat': 'グローバルチャット', 'admin': '管理・ログ', 'welcome': 'ようこそカード' };
    return names[tab] || '';
}

// サーバー情報画面の描画
function renderServerInfo(server) {
    const contentArea = document.querySelector('.content');
    contentArea.innerHTML = `
        <div class="manage-container">
            <h1>📊 サーバー情報: ${server.name}</h1>
            
            <div class="stats-overview">
                <div class="stat-mini-card">
                    <span class="label">メンバー数</span>
                    <span class="value" id="member-count">--</span>
                </div>
                <div class="stat-mini-card">
                    <span class="label">今日のメッセージ</span>
                    <span class="value" id="msg-today">--</span>
                </div>
                <div class="stat-mini-card">
                    <span class="label">今週の参加</span>
                    <span class="value" id="join-week" style="color: #3ba55c;">+--</span>
                </div>
                <div class="stat-mini-card">
                    <span class="label">今週の脱退</span>
                    <span class="value" id="leave-week" style="color: #ed4245;">---</span>
                </div>
            </div>

            <div class="charts-grid">
                <div class="settings-card">
                    <h3>💬 メッセージ送信件数 (直近7日間)</h3>
                    <canvas id="msgChart"></canvas>
                </div>
                <div class="settings-card">
                    <h3>👥 メンバー参加・脱退推移</h3>
                    <canvas id="memberChart"></canvas>
                </div>
            </div>
        </div>
    `;

    // グラフの描画（Chart.jsを使用）
    initCharts();
    
    // 本来はここで fetch(`/api/server-stats/${server.id}`) してデータを取得し、
    // innerText を書き換える処理を入れます。
}

function initCharts() {
    // スクリプトタグを動的に読み込む（HTMLに直接書いてもOK）
    if (typeof Chart === 'undefined') {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
        script.onload = () => drawDemoCharts();
        document.head.appendChild(script);
    } else {
        drawDemoCharts();
    }
}

function drawDemoCharts() {
    // メッセージ数のグラフ
    new Chart(document.getElementById('msgChart'), {
        type: 'line',
        data: {
            labels: ['月', '火', '水', '木', '金', '土', '日'],
            datasets: [{
                label: 'メッセージ数',
                data: [120, 190, 150, 250, 200, 300, 450],
                borderColor: '#5865f2',
                tension: 0.4,
                fill: true,
                backgroundColor: 'rgba(88, 101, 242, 0.1)'
            }]
        },
        options: { plugins: { legend: { display: false } } }
    });

    // 参加・脱退のグラフ
    new Chart(document.getElementById('memberChart'), {
        type: 'bar',
        data: {
            labels: ['月', '火', '水', '木', '金', '土', '日'],
            datasets: [
                { label: '参加', data: [10, 15, 8, 12, 20, 25, 30], backgroundColor: '#3ba55c' },
                { label: '脱退', data: [-2, -5, -3, -1, -8, -4, -10], backgroundColor: '#ed4245' }
            ]
        },
        options: { scales: { y: { stacked: false } } }
    });
}

function renderSecuritySettings(server) {
    const contentArea = document.querySelector('.content');
    contentArea.innerHTML = `
        <div class="manage-container">
            <h1 class="page-title">🛡️ モデレーション設定</h1>

            <div class="settings-card">
                <h3 class="section-title">アンチスパム</h3>
                ${renderToggleItem("msg_spam", "メッセージスパムのブロック", `
                    <div class="input-inline">
                        <input type="number" value="5" min="1"> 回 / 
                        <input type="number" value="3" min="1"> 秒間
                    </div>
                `)}
                ${renderToggleItem("file_spam", "添付ファイルスパムのブロック", `
                    <div class="input-inline">最大 <input type="number" value="3" min="1"> 枚まで</div>
                `)}
                ${renderToggleItem("emoji_spam", "絵文字スパムのブロック", `
                    <div class="input-inline">最大 <input type="number" value="10" min="1"> 個まで</div>
                `)}
                ${renderToggleItem("line_spam", "改行スパムのブロック", `
                    <div class="input-inline">最大 <input type="number" value="15" min="1"> 行まで</div>
                `)}
            </div>

            <div class="settings-card">
                <h3 class="section-title">Automod</h3>
                ${renderSelectItem("invite", "招待リンクのブロック")}
                ${renderSelectItem("danger", "危険サイトのブロック")}
                ${renderSelectItem("nsfw", "NSFWサイトのブロック")}
                ${renderSelectItem("ngword", "NGワードのブロック")}
            </div>

            <div class="settings-card">
                <h3 class="section-title">NGワード管理</h3>

                <div class="action-row" style="margin-bottom: 15px;">
                    <input type="text" class="discord-input" placeholder="新しいワードを追加...">
                    <button class="btn-add">追加</button>
                    <button class="btn-delete-small">選択したワードを削除</button>
                </div>

                <div class="ng-word-list">
                    <label><input type="checkbox"> word1</label>
                    <label><input type="checkbox"> word2</label>
                </div>
            </div>

            <div class="settings-card">
                <h3 class="section-title">例外設定 (チャンネル)</h3>
                <div class="action-row" style="margin-bottom: 15px;">
                    <button class="btn-add" onclick="openExceptionModal('channel')">チャンネルを追加</button>
                    <button class="btn-delete-small">選択した設定を削除</button>
                </div>
    
                <div class="ng-word-list" style="height: auto; min-height: 100px;">
                    <label class="exception-item">
                        <input type="checkbox">
                        <div class="exception-info">
                            <strong>#🔧-test-room</strong>
                            <span>許可項目: 招待リンク, NGワード, スパム</span>
                        </div>
                    </label>
                </div>
            </div>

            <div class="settings-card">
                <h3 class="section-title">例外設定 (ユーザー)</h3>
                <div class="action-row" style="margin-bottom: 15px;">
                    <button class="btn-add" onclick="openExceptionModal('user')">ユーザーを追加</button>
                    <button class="btn-delete-small">選択した設定を削除</button>
                </div>

                <div class="ng-word-list" style="height: auto; min-height: 100px;">
                    <p class="hint">現在、例外に設定されているユーザーはいません。</p>
                </div>
            </div>

            <div class="settings-card">
                <h3 class="section-title">オートキック</h3>
                
                <div class="kick-rules-section" style="margin-bottom: 30px;">
                    <p class="setting-label">ルール</p>
                    ${renderToggleItem("sus_acc", "不審なアカウント", `
                        <div class="input-inline">作成から <input type="number" value="1" min="1"> 日以内</div>
                    `)}
                    ${renderToggleItem("unverified_bot", "未認証Bot", "")}
                    ${renderToggleItem("no_avatar", "アバターのないアカウント", "")}
                </div>

                <div class="whitelist-box">
                    <p class="setting-label">ホワイトリスト</p>
                    
                    <div class="action-row" style="margin-bottom: 10px;">
                        <button class="btn-delete-small">選択したユーザーを削除</button>
                    </div>

                    <p class="hint" style="margin-bottom: 10px; font-size: 12px; color: #b9bbbe;">
                        ※ ホワイトリストへの追加は、サーバーログの各ユーザー項目から行えます。
                    </p>
    
                    <div class="ng-word-list" style="max-height: 150px; background: #111214;">
                        <label class="exception-item">
                            <input type="checkbox"> 
                            <div class="exception-info">
                                <strong>User#0001</strong>
                                <span>ID: 123456789012345678</span>
                            </div>
                        </label>
                    </div>
                </div>
            </div>

            <div class="save-footer">
                <button class="btn-save-large">設定を保存する</button>
            </div>
        </div>
    `;
}

// 共通パーツ：トグル＋展開メニュー
function renderToggleItem(id, label, subContent) {
    return `
        <div class="setting-item-container">
            <div class="setting-item">
                <span class="label">${label}</span>
                <label class="switch">
                    <input type="checkbox" onchange="document.getElementById('sub-${id}').classList.toggle('active', this.checked)">
                    <span class="slider"></span>
                </label>
            </div>
            ${subContent ? `<div id="sub-${id}" class="sub-settings">${subContent}</div>` : ''}
        </div>
    `;
}

// 共通パーツ：セレクトメニュー
function renderSelectItem(id, label) {
    return `
        <div class="setting-item">
            <span class="label">${label}</span>
            <select class="discord-select">
                <option value="none">無効</option>
                <option value="delete">メッセージを削除</option>
                <option value="timeout">削除してタイムアウト</option>
            </select>
        </div>
    `;
}

// モーダルを表示する関数
function openExceptionModal(type) {
    const modalHtml = `
        <div id="exception-modal" class="modal-overlay">
            <div class="modal-content">
                <h2>${type === 'channel' ? 'チャンネル' : 'ユーザー'}の例外設定を追加</h2>
                
                <div class="setting-group">
                    <span class="setting-label">対象を選択</span>
                    <select class="discord-select" style="width: 100%;">
                        <option>選択してください...</option>
                        </select>
                </div>

                <div class="setting-group">
                    <span class="setting-label">例外（無視）にする項目</span>
                    <div class="checkbox-grid">
                        <label><input type="checkbox"> 招待リンクの送信</label>
                        <label><input type="checkbox"> 詐欺サイトURLの送信</label>
                        <label><input type="checkbox"> NSFWサイトの送信</label>
                        <label><input type="checkbox"> NGワードの送信</label>
                        <label><input type="checkbox"> メッセージスパム</label>
                        <label><input type="checkbox"> 添付ファイルスパム</label>
                        <label><input type="checkbox"> 絵文字スパム</label>
                        <label><input type="checkbox"> 過剰改行の防止</label>
                        <label><input type="checkbox"> ログの記録</label>
                    </div>
                </div>

                <div class="modal-footer">
                    <button class="btn-save" onclick="closeModal()">追加する</button>
                    <button class="btn-cancel" onclick="closeModal()">キャンセル</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('exception-modal');
    modal.addEventListener('click', (e) => {
        // クリックされたのが「modal-content」の外側（つまりoverlay）なら閉じる
        if (e.target === modal) {
            closeModal();
        }
    });
}

function closeModal() {
    const modal = document.getElementById('exception-modal');
    if (modal) modal.remove();
}

function renderEconomySettings(server) {
    const contentArea = document.querySelector('.content');
    contentArea.innerHTML = `
        <div class="manage-container">
            <h1 class="page-title">💰 経済システム設定</h1>

            <div class="settings-card">
                <h3 class="section-title">デフォルトクールダウン設定</h3>
                <p class="hint" style="margin-bottom: 20px;">各コマンドを実行できるまでの待ち時間（分）を設定します。</p>
                <div class="grid-2col">
                    ${renderInputItem("cd_work", "仕事", 10)}
                    ${renderInputItem("cd_fish", "魚釣り", 5)}
                    ${renderInputItem("cd_rob", "強盗 (プレイヤー)", 60)}
                    ${renderInputItem("cd_crime", "犯罪", 15)}
                    ${renderInputItem("cd_bank", "銀行強盗", 120)}
                    ${renderInputItem("cd_beg", "乞食", 3)}
                </div>
            </div>

            <div class="settings-card">
                <h3 class="section-title">クールダウンの強制解除</h3>
                <div class="action-row" style="align-items: flex-end; gap: 15px;">
                    <div style="flex: 1.5; position: relative;">
                        <span class="setting-label">対象ユーザーを選択</span>
                        <div class="user-search-container">
                            <input type="text" id="user-search-input" class="discord-input" 
                                placeholder="名前やIDで検索..." oninput="filterUserList()">
                            <div id="user-search-dropdown" class="search-results-dropdown">
                                <div class="search-item" onclick="selectUser('1234', 'User#0001')">User#0001 (1234...)</div>
                            </div>
                        </div>
                    </div>
                    <div style="flex: 1;">
                        <span class="setting-label">項目</span>
                        <select class="discord-select" style="width: 100%;">
                            <option>すべて</option>
                            <option>仕事</option>
                            <option>魚釣り</option>
                            <option>強盗</option>
                            <option>犯罪</option>
                            <option>銀行強盗</option>
                            <option>乞食</option>
                            </select>
                    </div>
                    <button class="btn-save" style="height: 44px; white-space: nowrap;">解除する</button>
                </div>
            </div>

            <div class="settings-card">
                <h3 class="section-title">宝くじの通知</h3>
                <span class="setting-label">通知チャンネル</span>
                <select class="discord-select" style="width: 100%;">
                    <option>無効</option>
                    <option>#general</option>
                    <option>#lottery-log</option>
                </select>
            </div>

            <div class="settings-card" style="border-color: #ed4245;">
                <h3 class="section-title" style="color: #ed4245;">データリセット</h3>
                <p class="hint">これらは取り消しができません。慎重に操作してください。</p>
                <div class="action-row" style="flex-wrap: wrap;">
                    <button class="btn-delete-small" onclick="handleResetRequest('ユーザーデータ')">ユーザーデータ</button>
                    <button class="btn-delete-small" onclick="handleResetRequest('クールダウン')">クールダウン</button>
                    <button class="btn-delete-small" onclick="handleResetRequest('リーダーボード')">リーダーボード</button>
                    <button class="btn-delete-small" onclick="handleResetRequest('全サーバーデータ')">サーバーデータ</button>
                </div>
            </div>

            <div class="save-footer">
                <button class="btn-save-large">設定を保存する</button>
            </div>
        </div>
    `;
}

// ヘルパー：入力項目
function renderInputItem(id, label, defaultValue) {
    return `
        <div class="setting-item">
            <span class="label">${label}</span>
            <div class="input-inline">
                <input type="number" id="${id}" value="${defaultValue}" min="0"> 分
            </div>
        </div>
    `;
}

// リセット確認モーダル
function openResetModal(target) {
    const modalHtml = `
        <div id="reset-modal" class="modal-overlay">
            <div class="modal-content" style="border-top: 5px solid #ed4245;">
                <h2 style="color: #ed4245;">⚠️ 本当にリセットしますか？</h2>
                <p style="margin: 20px 0; line-height: 1.6;">
                    <strong>「${target}」</strong>をすべて削除しようとしています。<br>
                    この操作は取り消すことができません。
                </p>
                <div class="modal-footer">
                    <button class="btn-delete-small" style="padding: 10px 20px;" onclick="closeResetModal()">リセットを実行する</button>
                    <button class="btn-cancel" onclick="closeResetModal()">キャンセル</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // 背景クリックで閉じる
    const modal = document.getElementById('reset-modal');
    modal.addEventListener('click', (e) => { if (e.target === modal) closeResetModal(); });
}

function closeResetModal() {
    const modal = document.getElementById('reset-modal');
    if (modal) {
        modal.classList.add('closing');
        // アニメーションが終わってから削除
        setTimeout(() => modal.remove(), 200);
    }
}

// openUserSelectResetModal 内の onclick="closeModal()" も 
// 全て onclick="closeResetModal()" に統一すると確実です。

// 検索入力時の処理
// 検索入力時の処理（引数にデフォルト値を設定してエラーを防ぐ）
function filterUserList(inputId = 'user-search-input', dropdownId = 'user-search-dropdown') {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    
    if (!input || !dropdown) return;

    const filter = input.value.toLowerCase();
    
    if (!filter) {
        dropdown.classList.remove('show');
        return;
    }

    // デモ用データ（本来はAPIから取得）
    const demoUsers = [
        {id: '123456789', name: 'User#0001'},
        {id: '555666777', name: 'Discord_Admin'}
    ];

    const matched = demoUsers.filter(u => u.name.toLowerCase().includes(filter) || u.id.includes(filter));

    if (matched.length > 0) {
        dropdown.classList.add('show');
        dropdown.innerHTML = matched.map(u => `
            <div class="search-item" onclick="${inputId === 'reset-user-search' 
                ? `selectUserForReset('${u.id}', '${u.name}')` 
                : `selectUser('${u.id}', '${u.name}')`}">
                ${u.name} <small>(${u.id})</small>
            </div>
        `).join('');
    } else {
        dropdown.innerHTML = '<div class="search-item">見つかりません</div>';
        dropdown.classList.add('show');
    }
}

// ユーザーを選択した時
function selectUser(id, name) {
    const input = document.getElementById('user-search-input');
    const dropdown = document.getElementById('user-search-dropdown');
    
    input.value = `${name} (${id})`; // 表示を更新
    dropdown.classList.remove('show');
    
    // ここで選択されたIDをどこかに保持しておく（保存用）
    input.dataset.selectedId = id;
}

// 外側をクリックしたら閉じる処理を共通化しておくと便利
window.addEventListener('click', (e) => {
    if (!e.target.closest('.user-search-container')) {
        document.getElementById('user-search-dropdown')?.classList.remove('show');
    }
});

// 経済設定画面内のボタンのonclickを変更
// <button class="btn-delete-small" onclick="handleResetRequest('ユーザーデータ')">ユーザーデータ</button>

function handleResetRequest(target) {
    if (target === 'ユーザーデータ') {
        openUserSelectResetModal();
    } else {
        openResetModal(target); // 従来の全員リセット確認
    }
}

// 特定のユーザーを選ぶためのモーダル
function openUserSelectResetModal() {
    const modalHtml = `
        <div id="reset-modal" class="modal-overlay">
            <div class="modal-content" style="border-top: 5px solid #ed4245; width: 500px;">
                <h2 style="color: #ed4245;">👤 ユーザーデータの個別リセット</h2>
                <p class="hint" style="margin-top: 10px;">リセットしたいユーザーを検索して選択してください。</p>
                
                <div class="user-search-container" style="margin: 20px 0;">
                    <input type="text" id="reset-user-search" class="discord-input" 
                           placeholder="名前やIDで検索..." oninput="filterUserList('reset-user-search', 'reset-dropdown')">
                    <div id="reset-dropdown" class="search-results-dropdown">
                        </div>
                </div>

                <div id="selected-user-info" style="display: none; background: rgba(237, 66, 69, 0.1); padding: 15px; border-radius: 4px; margin-bottom: 20px;">
                    <p style="font-size: 14px;">選択中: <strong id="selected-user-name">---</strong></p>
                    <p style="font-size: 12px; color: #8e9297;">このユーザーの所持金、アイテム、経験値がすべて初期化されます。</p>
                </div>

                <div class="modal-footer">
                    <button id="execute-reset-btn" class="btn-delete-small" style="opacity: 0.5; pointer-events: none;" onclick="confirmUserReset()">リセットを実行</button>
                    <button class="btn-cancel" onclick="closeResetModal()">キャンセル</button>
                </div>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
}

// ユーザー選択時の処理（検索結果から呼ばれる）
function selectUserForReset(id, name) {
    document.getElementById('selected-user-info').style.display = 'block';
    document.getElementById('selected-user-name').innerText = `${name} (${id})`;
    
    // 実行ボタンを有効化
    const btn = document.getElementById('execute-reset-btn');
    btn.style.opacity = '1';
    btn.style.pointer_events = 'auto';
    btn.dataset.userId = id; // IDを保持
    
    document.getElementById('reset-dropdown').classList.remove('show');
}