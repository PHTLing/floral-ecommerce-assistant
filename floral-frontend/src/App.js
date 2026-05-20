import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from 'react-markdown';
import axios from "axios";
import { Send, Phone } from "lucide-react";
import { motion } from "framer-motion";

const QUICK_REPLIES = [
  "🎂 Mẫu hoa tặng sinh nhật",
  "💕 Mẫu hoa bày tỏ tình yêu",
  "🎓 Mẫu hoa chúc mừng"
];

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [userHasResponded, setUserHasResponded] = useState(false);
  const chatRef = useRef(null);

  const session_id = "user_123";

  // Khởi tạo greeting message lúc app start
  useEffect(() => {
    const greetingMsg = {
      type: "bot",
      text: "Xin chào! 👋 Tôi là FloraConsult - chatbot tư vấn hoa của bạn.\nBạn cần mình giúp gì hôm nay?",
      isGreeting: true,
      data: []
    };
    setMessages([greetingMsg]);
  }, []);

  // Auto scroll
  useEffect(() => {
    chatRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text) => {
    if (!text.trim()) return;

    // Đánh dấu user đã phản hồi lần đầu
    if (!userHasResponded) {
      setUserHasResponded(true);
    }

    const userMsg = { type: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    try {
      const res = await axios.post("http://127.0.0.1:8000/chat", {
        user_input: text,
        session_id,
      });

      const botMsg = {
        type: "bot",
        text: res.data.reply,
        data: res.data.data || [],
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      
      {/* HEADER */}
      <div className="bg-white p-4 flex justify-between items-center shadow">
        <div className="flex items-center gap-3">
          <img
            src="bouquet.png"
            alt="logo"
            className="w-10"
          />
          <div>
            <h1 className="font-bold text-lg">FloraConsult</h1>
            <p className="text-sm text-gray-500">
              Tư vấn hoa trực tuyến
            </p>
          </div>
        </div>

        <button className="bg-green-500 text-white px-4 py-2 rounded-full flex items-center gap-2">
          <Phone size={16} />
          Gọi ngay
        </button>
      </div>

      {/* CHAT */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {msg.type === "user" ? (
              <div className="flex justify-end">
                <div className="bg-green-500 text-white px-4 py-2 rounded-2xl max-w-md">
                  {msg.text}
                </div>
              </div>
            ) : (
              <div>
                {/* Bot text */}
                {/* <div className="bg-pink-100 px-4 py-2 rounded-2xl max-w-xs">
                  {msg.text}
                </div> */}
                <div className="bg-pink-100 px-4 py-2 rounded-2xl max-w-md  text-sm">
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                </div>

                {/* Quick replies - Chỉ hiển thị nếu user chưa phản hồi và đây là message cuối cùng */}
                {!userHasResponded && idx === messages.length - 1 && (
                  <div className="flex gap-2 mt-2 flex-wrap">
                    {QUICK_REPLIES.map((q, i) => (
                      <button
                        key={i}
                        onClick={() => sendMessage(q)}
                        className="bg-white border px-3 py-1 rounded-full text-sm hover:bg-gray-100"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}

                {/* Product carousel */}
                {msg.data && msg.data.length > 0 && (
                  <div className="flex overflow-x-auto gap-4 mt-3 pb-2">
                    {msg.data.map((item, i) => (
                      <div
                        key={i}
                        className="min-w-[200px] bg-white rounded-xl shadow p-3"
                      >
                        {item.image ? (
                          <img
                            src={item.image}
                            alt={item.name}
                            className="w-full h-32 object-cover rounded-lg"
                            onError={(e) => e.target.src = 'https://via.placeholder.com/200x150?text=Hoa'}
                          />
                          ) : (
                          <div className="w-full h-32 bg-gray-200 rounded-lg flex items-center justify-center text-gray-500 text-sm">
                            Chưa có hình ảnh
                          </div>
                        )}
                        <h3 className="font-semibold mt-2">
                          {item.name}
                        </h3>
                        <p className="text-green-600">
                          {item.price}
                        </p>
                        <a 
                          href={item.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="mt-2 block w-full bg-green-500 text-white py-2 rounded-lg text-center font-semibold hover:bg-green-600 transition-colors"
                        >
                          Xem chi tiết
                        </a>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </motion.div>
        ))}

        <div ref={chatRef}></div>
      </div>

      {/* INPUT */}
      <div className="p-4 bg-white flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Nhập tin nhắn..."
          className="flex-1 border rounded-full px-4 py-2 outline-none"
          onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
        />

        <button
          onClick={() => sendMessage(input)}
          className="bg-green-500 text-white p-3 rounded-full"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}