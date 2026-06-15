<template>
  <section class="card">
    <div class="card__header">
      <div>
        <p class="eyebrow">Steam 商店卡片</p>
        <h3>当前折扣</h3>
      </div>
      <span class="badge">{{ deals.items.length }} 项</span>
    </div>

    <div v-if="loading" class="deal-list">
      <div v-for="index in 3" :key="index" class="deal-skeleton"></div>
    </div>

    <div v-else-if="!deals.configured" class="empty-state">
      <p class="empty-state__title">商店卡片待解锁</p>
      <p class="empty-state__text">{{ deals.message }}</p>
    </div>

    <div v-else>
      <p v-if="deals.message" class="inline-error">{{ deals.message }}</p>

      <div v-if="deals.items.length" class="deal-list">
        <a
          v-for="item in deals.items"
          :key="item.appid"
          class="deal-item"
          :href="item.storeUrl"
          target="_blank"
          rel="noopener"
        >
          <img :src="item.headerImage" :alt="item.name">
          <div class="deal-item__content">
            <div class="deal-item__title">
              <strong>{{ item.name }}</strong>
              <span>{{ item.discountPercent }}% OFF</span>
            </div>
            <div class="deal-item__price">
              <strong>¥{{ formatPrice(item.finalPrice) }}</strong>
              <span v-if="item.originalPrice">¥{{ formatPrice(item.originalPrice) }}</span>
            </div>
          </div>
        </a>
      </div>

      <p v-else class="muted">当前没有可展示的商店折扣。</p>
    </div>
  </section>
</template>

<script>
export default {
  name: 'SteamDealsCard',
  props: {
    deals: {
      type: Object,
      required: true,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  methods: {
    formatPrice(value) { return Number(value || 0).toFixed(2) },
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

.badge {
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(61, 126, 255, 0.1);
  color: #3656d8;
  font-size: 12px;
}

.deal-list {
  display: grid;
  gap: 12px;
}

.deal-item {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  gap: 14px;
  padding: 12px;
  border-radius: 22px;
  background: rgba(248, 250, 255, 0.94);
  text-decoration: none;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.deal-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 26px rgba(17, 45, 79, 0.12);
}

.deal-item img {
  width: 84px;
  height: 56px;
  border-radius: 16px;
  object-fit: cover;
}

.deal-item__title,
.deal-item__price {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.deal-item__title strong,
.deal-item__price strong {
  color: #102542;
}

.deal-item__title span {
  color: #227a52;
  font-size: 12px;
  white-space: nowrap;
}

.deal-item__price {
  margin-top: 10px;
  align-items: center;
}

.deal-item__price span {
  color: #7d8ca0;
  font-size: 13px;
  text-decoration: line-through;
}

.deal-skeleton {
  height: 80px;
  border-radius: 22px;
  background: linear-gradient(90deg, rgba(233, 239, 248, 0.65), rgba(255, 255, 255, 0.92), rgba(233, 239, 248, 0.65));
  background-size: 200% 100%;
  animation: shimmer 1.2s infinite linear;
}

.empty-state__title {
  color: #102542;
}

.empty-state__title {
  margin: 0 0 8px;
  font-size: 18px;
}

.empty-state__text,
.muted {
  margin: 0;
  color: #607086;
  line-height: 1.6;
}

.inline-error {
  margin: 0 0 14px;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 120, 120, 0.12);
  color: #a33b44;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
