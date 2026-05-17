import axios from "axios"

const api = axios.create({
    baseURL: "http://127.0.0.1:8000",
    timeout: 600000
})

export const chatAPI = (question, k=3) => {

    return api.post("/chat", {
        question,
        k
    })
}