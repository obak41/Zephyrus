// メニューの開閉
function toggleMenu() {
    document.getElementById("nav-menu").classList.toggle("active");
}

// 統計の更新
async function updateDashboardStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        // デバッグ用：ブラウザのコンソールに中身を表示させる
        console.log("取得したデータ:", data);

        const serverElement = document.getElementById('stat-servers');
        const userElement = document.getElementById('stat-users');

        // データの中身が server_count なのか guilds なのか、どちらでも動くようにする
        const guilds = data.guilds || data.server_count || 0;
        const users = data.users || data.user_count || 0;

        if (serverElement) {
            serverElement.innerText = guilds.toLocaleString() + " サーバー";
        }
        if (userElement) {
            userElement.innerText = users.toLocaleString() + " ユーザー";
        }
    } catch (error) {
        console.error("統計データの反映に失敗:", error);
    }
}

// ログイン状態の確認
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/user');
        if (response.ok) {
            const user = await response.json();
            const loginButtons = document.querySelectorAll('a[href="/auth/login"]');
            loginButtons.forEach(btn => {
                btn.innerText = "ダッシュボードへ";
                // ログイン済みならログインリンクを無効化、または別のページへ
                btn.href = "#"; 
            });
            console.log(`${user.username} でログイン中`);
        }
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
    updateDashboardStats();
    checkAuthStatus();
});