<template>
  <section class="card">
    <div class="card__header">
      <div>
        <p class="eyebrow">Steam 个人概览</p>
        <h3>玩家状态</h3>
      </div>
      <button class="refresh-button" type="button" :disabled="loading" @click="$emit('refresh')">
        刷新
      </button>
    </div>

    <div v-if="loading" class="skeleton-grid">
      <div class="skeleton skeleton--hero"></div>
      <div class="skeleton"></div>
      <div class="skeleton"></div>
    </div>

    <div v-else-if="!overview.profile" class="empty-state">
      <p class="empty-state__title">Steam 信息未配置</p>
      <p class="empty-state__text">{{ overview.message }}</p>
    </div>

    <div v-else class="overview">
      <div class="hero">
        <img :src="overview.profile.avatarUrl" :alt="overview.profile.personaName">
        <div>
          <strong>{{ overview.profile.personaName }}</strong>
          <p>{{ overview.profile.status }}</p>
          <a :href="overview.profile.profileUrl" target="_blank" rel="noopener">打开 Steam 主页</a>
        </div>
      </div>

      <div v-if="overview.stats" class="stats">
        <div class="stat">
          <span>拥有游戏</span>
          <strong>{{ overview.stats.ownedGamesCount }}</strong>
        </div>
        <div class="stat">
          <span>最近游戏</span>
          <strong>{{ overview.stats.recentGamesCount }}</strong>
        </div>
        <div class="stat">
          <span>两周时长</span>
          <strong>{{ overview.stats.recentPlaytimeHours }}h</strong>
        </div>
      </div>

      <div class="current-game">
        <p>当前状态</p>
        <strong>{{ overview.profile.currentGame || '当前没有在玩游戏' }}</strong>
      </div>

      <div v-if="overview.message" class="inline-error">
        {{ overview.message }}
      </div>

      <div class="recent-games">
        <div class="recent-games__header">
          <span>最近常玩</span>
          <small>{{ overview.recentGames.length }} 款</small>
        </div>
        <div v-if="overview.recentGames.length" class="recent-games__list">
          <article v-for="game in overview.recentGames" :key="game.appid" class="game-card">
            <img :src="game.iconUrl || game.headerImage" :alt="game.name">
            <div>
              <strong>{{ game.name }}</strong>
              <p>近两周 {{ game.playtime2WeeksHours }}h</p>
              <small>总时长 {{ game.playtimeForeverHours }}h</small>
            </div>
          </article>
        </div>
        <p v-else class="muted">最近没有可展示的游戏数据。</p>
      </div>
    </div>
  </section>
</template>

<script>
export default {
  name: 'SteamOverviewCard',
  props: {
    overview: {
      type: Object,
      required: true,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
}
</script>

<style lang="less" scoped>
.card {
  padding: 22px;
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow: 0 20px 40px rgba(13, 42, 78, 0.12);
}

.card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.eyebrow {
  margin: 0 0 6px;
  color: rgba(35, 56, 102, 0.64);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h3 {
  margin: 0;
  color: #102542;
  font-size: 22px;
}

.refresh-button {
  border: 0;
  border-radius: 16px;
  padding: 10px 14px;
  background: rgba(237, 243, 255, 0.96);
  color: #3656d8;
  cursor: pointer;
}

.refresh-button:disabled {
  opacity: 0.45;
}

.empty-state {
  padding: 18px 0 8px;
  color: #607086;
}

.empty-state__title {
  margin: 0 0 8px;
  font-size: 18px;
  color: #102542;
}

.empty-state__text {
  margin: 0;
  line-height: 1.6;
}

.hero {
  display: grid;
  grid-template-columns: 68px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
}

.hero img {
  width: 68px;
  height: 68px;
  object-fit: cover;
  border-radius: 22px;
  box-shadow: 0 12px 24px rgba(17, 45, 79, 0.14);
}

.hero strong {
  display: block;
  color: #102542;
  font-size: 18px;
}

.hero p,
.hero a {
  margin: 6px 0 0;
  color: #607086;
  text-decoration: none;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0;
}

.stat {
  padding: 14px;
  border-radius: 22px;
  background: rgba(243, 247, 255, 0.96);
}

.stat span,
.current-game p,
.recent-games__header small {
  color: #607086;
  font-size: 13px;
}

.stat strong,
.current-game strong {
  display: block;
  margin-top: 6px;
  color: #102542;
}

.current-game {
  padding: 14px;
  border-radius: 22px;
  background: rgba(230, 240, 255, 0.7);
}

.current-game p {
  margin: 0 0 6px;
}

.inline-error {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 120, 120, 0.12);
  color: #a33b44;
}

.recent-games {
  margin-top: 18px;
}

.recent-games__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  color: #102542;
}

.recent-games__list {
  display: grid;
  gap: 10px;
}

.game-card {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  padding: 12px;
  border-radius: 20px;
  background: rgba(248, 250, 255, 0.94);
}

.game-card img {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  object-fit: cover;
}

.game-card strong {
  display: block;
  color: #102542;
}

.game-card p,
.game-card small,
.muted {
  margin: 4px 0 0;
  color: #607086;
}

.skeleton-grid {
  display: grid;
  gap: 12px;
}

.skeleton {
  height: 72px;
  border-radius: 22px;
  background: linear-gradient(90deg, rgba(233, 239, 248, 0.65), rgba(255, 255, 255, 0.92), rgba(233, 239, 248, 0.65));
  background-size: 200% 100%;
  animation: shimmer 1.2s infinite linear;
}

.skeleton--hero {
  height: 92px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (max-width: 720px) {
  .stats {
    grid-template-columns: 1fr;
  }
}
</style>
