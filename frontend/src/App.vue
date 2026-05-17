<template>
  <div id="app">
    
    <div class="App">
      <div class="box" @click="fn"></div>
    </div>
    <ChatAgent></ChatAgent>
  </div>
</template>

<script>

import ChatAgent from './components/ChatAgent.vue'

export default {
  name: 'App',
  components: {
    ChatAgent
  },
  created(){
    console.log('我是created')
  },
  methods: {
    fn(){
      alert('你好')
    },
    
  },
}
</script>

<style lang="less">
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}

.App {
  width: 400px;
  height: 400px;
  background-color: pink;
  .box {
    width: 100px;
    height: 100px;
    background-color: skyblue;
  }
}

</style>
