document.addEventListener('DOMContentLoaded', function() {
    const refreshBtn = document.getElementById('refresh-btn');
    const filterBtn = document.getElementById('filter-btn');
    const saunaGrid = document.getElementById('sauna-grid');
    const saunaCards = document.querySelectorAll('.sauna-card');
    let showHiddenGemsOnly = false;

    // サウナカードにフェードインアニメーションを追加
    const cards = document.querySelectorAll('.sauna-card');
    cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
        card.classList.add('fade-in');
    });

    // 情報更新ボタンのクリックイベント
    refreshBtn.addEventListener('click', async function() {
        try {
            const response = await fetch('/api/saunas');
            const data = await response.json();
            location.reload();
        } catch (error) {
            console.error('Error fetching sauna data:', error);
            alert('データの更新に失敗しました。');
        }
    });

    // 穴場フィルターボタンのクリックイベント
    filterBtn.addEventListener('click', function() {
        showHiddenGemsOnly = !showHiddenGemsOnly;
        filterBtn.textContent = showHiddenGemsOnly ? 'すべて表示' : '穴場のみ表示';
        filterBtn.classList.toggle('bg-green-500');
        filterBtn.classList.toggle('bg-gray-500');
        filterSaunas();
    });

    // サウナグリッドの更新
    function updateSaunaGrid(saunas) {
        saunaGrid.innerHTML = '';
        saunas.forEach((sauna, index) => {
            const card = createSaunaCard(sauna, index);
            saunaGrid.appendChild(card);
        });
    }

    // サウナカードの作成
    function createSaunaCard(sauna, index) {
        const card = document.createElement('div');
        card.className = 'bg-white rounded-lg shadow-md overflow-hidden sauna-card';
        card.style.animationDelay = `${index * 0.1}s`;
        card.classList.add('fade-in');

        card.innerHTML = `
            <div class="p-6">
                <h2 class="text-xl font-semibold mb-2">${sauna.name}</h2>
                <p class="text-gray-600 mb-2">料金: ${sauna.price}</p>
                ${sauna.is_hidden_gem ? `
                    <span class="inline-block bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded-full mb-4">
                        穴場サウナ
                    </span>
                ` : ''}
                <div class="flex items-center justify-between">
                    <span class="text-sm text-gray-500">レビュー数: ${sauna.review_count}</span>
                    <a href="${sauna.url}" target="_blank" class="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
                        詳細を見る
                    </a>
                </div>
            </div>
        `;

        return card;
    }

    // サウナのフィルタリング
    function filterSaunas() {
        saunaCards.forEach(card => {
            const isHiddenGem = card.querySelector('.bg-yellow-100') !== null;
            card.classList.toggle('hidden', !isHiddenGem);
        });
    }
}); 