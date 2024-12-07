# service-assistant-mini
Telegram bot, written in Python, allows you to use a large number of neural networks for free.<br>

## Details
The library is used for free use of neural networks - https://github.com/xtekky/gpt4free and the g4f provider.Provider.Blackbox.<br>
To use gemini-1.5-flash and gemini-1.5-pro, you need the Gemini API key:
https://github.com/fakelag28/service-assistant-mini/blob/5c404563864c0db23e19446341950b68895f559c/main.py#L32
The interface for using the bot's telegrams and the comments in the code are written in Russian.

## Screenshots of the bot's telegram messages
<div class="row">
  <img src="https://github.com/fakelag28/service-assistant-mini/blob/main/docs/screen_3.png?raw=true" width=250>
  <img src="https://github.com/fakelag28/service-assistant-mini/blob/main/docs/screen_2.png?raw=true" width=250>
  <img src="https://github.com/fakelag28/service-assistant-mini/blob/main/docs/screen_1.png?raw=true" width=250>
</div>

## Installation and launch
First, you need to install all the necessary libraries, and then create the required tables for the MySQL database:
```mysql
CREATE TABLE `chats` (
  `chat_id` bigint(20) NOT NULL,
  `user_id` bigint(20) DEFAULT NULL,
  `message` text,
  `is_user_message` tinyint(1) DEFAULT NULL,
  `timestamp` datetime DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `neural_network_limits` (
  `network_name` varchar(255) NOT NULL,
  `usage_count` int(11) DEFAULT '0',
  `last_used` date DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `users` (
  `user_id` bigint(20) NOT NULL,
  `model_text` varchar(255) DEFAULT 'gpt-4o',
  `model_vision` varchar(255) NOT NULL,
  `model_image` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```
After that, create a telegram bot, and insert the received token into this line:
https://github.com/fakelag28/service-assistant-mini/blob/5c404563864c0db23e19446341950b68895f559c/main.py#L30
