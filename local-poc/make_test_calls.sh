#!/bin/bash
# Генерация синтетических тестовых «звонков»: стерео 16 кГц, левый канал = клиент,
# правый = оператор. Использует встроенный TTS macOS (Milena, ru_RU) и ffmpeg.
# Кейсы: живой разговор, автоответчик, спам-блокировщик.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p tmp test_data

VOICE="Milena"

mk_line() { # $1 имя, $2 темп (слов/мин), $3 текст
  say -v "$VOICE" -r "$2" -o "tmp/$1.aiff" "$3"
  ffmpeg -y -loglevel error -i "tmp/$1.aiff" -ar 16000 -ac 1 -c:a pcm_s16le "tmp/$1.wav"
}
mk_silence() { # $1 секунды, $2 имя
  ffmpeg -y -loglevel error -f lavfi -i "anullsrc=r=16000:cl=mono" -t "$1" -c:a pcm_s16le "tmp/$2.wav"
}
mk_beep() { # сигнал автоответчика
  ffmpeg -y -loglevel error -f lavfi -i "sine=frequency=880:duration=0.7" -ar 16000 -ac 1 -c:a pcm_s16le "tmp/$1.wav"
}
concat() { # $1 имя результата, далее фрагменты
  local out="$1"; shift
  : > "tmp/list_$out.txt"
  for f in "$@"; do echo "file '$PWD/tmp/$f.wav'" >> "tmp/list_$out.txt"; done
  ffmpeg -y -loglevel error -f concat -safe 0 -i "tmp/list_$out.txt" -c:a pcm_s16le "tmp/$out.wav"
}
stereo() { # $1 левый(клиент), $2 правый(оператор), $3 итог
  ffmpeg -y -loglevel error -i "tmp/$1.wav" -i "tmp/$2.wav" \
    -filter_complex "[0:a][1:a]join=inputs=2:channel_layout=stereo" -c:a pcm_s16le "test_data/$3.wav"
}

# ─── Звонок 1: живой разговор (продажа утепления) ───
mk_line o1 178 "Добрый день! Меня зовут Алексей, компания Стройдом. Вам удобно говорить?"
mk_line o2 172 "Мы звоним по вашему запросу про утепление дома. До конца месяца действует скидка двадцать процентов на работу под ключ."
mk_line o3 170 "Отлично! Оформляю заявку на бесплатный замер на завтра, с двенадцати до пятнадцати. Всего доброго!"
mk_line c1 155 "Да, здравствуйте, удобно, слушаю."
mk_line c2 150 "Расскажите, пожалуйста, сколько будет стоить утепление, если дом сто квадратов?"
mk_line c3 152 "Хорошо, давайте на завтра. Буду ждать мастера."
mk_silence 0.8 s08; mk_silence 1.0 s10; mk_silence 1.4 s14; mk_silence 0.5 s05
concat ch_live_oper o1 s10 o2 s14 o3
concat ch_live_client s08 c1 s10 c2 s10 c3
stereo ch_live_client ch_live_oper call_live
echo "call_live.wav готов"

# ─── Звонок 2: автоответчик ───
mk_line am1 150 "Здравствуйте. Вы позвонили Николаю. К сожалению, я не могу ответить. Оставьте ваше сообщение после сигнала."
mk_beep beep
mk_silence 2.0 s20
concat ch_am_client am1 beep s20
mk_line g1 175 "Добрый день, Николай! Компания Стройдом, удобно говорить?"
mk_line g2 170 "Алло? Не слышу вас. Перезвоним позже, всего доброго."
concat ch_am_oper g1 s14 g2
stereo ch_am_client ch_am_oper call_answer_machine
echo "call_answer_machine.wav готов"

# ─── Звонок 3: спам-блокировщик ───
mk_line robo1 148 "Внимание. Абонент отклонил звонок. Ваш номер внесён в чёрный список. Соединение будет завершено."
concat ch_spam_client robo1
mk_line g3 175 "Добрый день! Компания Веста, менеджер Ольга. Слышите меня?"
concat ch_spam_oper g3 s20
stereo ch_spam_client ch_spam_oper call_spam_block
echo "call_spam_block.wav готов"

rm -rf tmp
echo "Готово: $(ls test_data | wc -l | tr -d ' ') файла в test_data/"
