<template>
  <div id="app">
    <img alt="Vue logo" src="./assets/logo.png">
    <HelloWorld msg="Welcome to Your Vue.js App"/>
    <div class="App">
      <div class="box" @click="fn"></div>
    </div>
    <ChatAgent></ChatAgent>
  </div>
</template>

<script>

import HelloWorld from './components/HelloWorld.vue'
import ChatAgent from './components/ChatAgent.vue'

export default {
  name: 'App',
  components: {
    HelloWorld,
    ChatAgent
  },
  created(){
    console.log('我是created')
  },
  methods: {
    fn(){
      alert('你好')
    }
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
