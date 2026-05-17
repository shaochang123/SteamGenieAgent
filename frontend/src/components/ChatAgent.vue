<template>
    <div id="app">
        <h3>SteamGenieAgent</h3>
        <input v-model.trim="question" placeholder="请输入文本"/>
        <button @click="ask()">发送</button>
        <div class="answer" v-html="renderedMarkdown"></div>
    </div>
</template>

<script>
    import MarkdownIt from 'markdown-it';
    const md = new MarkdownIt()
    import { chatAPI } from '@/api/api';
    export default{
        name: 'ChatAgent',
        data(){
            return{
                question:"",
                answer:""
            }
            
        },
        methods: {
            async ask(){
                if(!this.question)return
                try{
                    const response = await chatAPI(
                        this.question
                    )
                    console.log(response.data)
                    this.answer = response.data.answer
                } catch (error) {
                    console.log(error)
                }
            }
            
        },
        computed: {
            renderedMarkdown() {
                return md.render(this.answer)
            }
        }
    }
</script>

<style>
#app{
    padding:20px;
}

input{
    width:300px;
    height:35px;
}

button{
    margin-left:10px;
    height:40px;
}

.answer{
    margin-top:20px;
    white-space: pre-wrap;
}
</style>