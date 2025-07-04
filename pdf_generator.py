<!DOCTYPE html>
<html lang="ru">

<head>
    <meta charset="UTF-8">
    <title>Тарифы доставки - China Together</title>
    <style>
        @page {
            size: A4;
            margin: 4mm;
        }

        body {
            font-family: 'DejaVu Sans', Arial, sans-serif;
            background-color: #ffffff;
            color: #333;
            margin: 0;
            padding: 0;
            font-size: 12px;
            line-height: 1.4;
        }

        /* .container {
            width: 100%;
            margin: 0;
            padding: 0;
        } */

        .header {
            text-align: center;
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 2px solid #E74C3C;
        }

        .logo {
            width: 80px;
            height: 80px;
            object-fit: cover;
            border-radius: 50%;
            margin-bottom: 0px;
            border: 3px solid #E74C3C;
            /* Яркий красный цвет без прозрачности */
            box-shadow: 0 4px 12px rgba(231, 76, 60, 0.4);
            /* Чуть теплее, чем раньше */
            background-color: #fff;
            /* Белый фон для лучшей видимости */
        }

        h1 {
            color: #E74C3C;
            font-size: 2.1rem;
            margin-bottom: 0px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }

        .subtitle {
            color: #666;
            font-size: 10px;
            margin: 0;
        }

        h2 {
            color: #ffffff;
            margin: 8px 0 6px 0;
            font-size: 14px;
            font-weight: bold;
            border-bottom: 1px solid #E74C3C;
            padding-bottom: 5px;
            text-transform: uppercase;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 8px;
            border: 1px solid #ddd;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        th,
        td {
            border: 1px solid #ddd;
            padding: 8px 8px;
            text-align: center;
            vertical-align: middle;
        }

        th {
            background-color: #f8f9fa;
            font-weight: bold;
            color: #2c3e50;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        td {
            font-size: 10px;
        }

        tr:nth-child(even) {
            background-color: #f9f9f9;
        }

        tr:hover {
            background-color: #fff3f2;
        }

        .additional-info {
            margin-top: 8px;
            font-size: 10px;
            line-height: 1.4;
            color: #555;
            background-color: #f8f9fa;
            padding: 12px;
            border-radius: 6px;
            border-left: 4px solid #E74C3C;
        }

        .additional-info h3 {
            margin: 0 0 8px 0;
            color: #E74C3C;
            font-size: 11px;
            font-weight: bold;
        }

        .additional-info ol {
            margin: 0;
            padding-left: 15px;
        }

        .additional-info li {
            margin-bottom: 4px;
        }

        .additional-info strong {
            color: #2c3e50;
        }

        .footer {
            text-align: center;
            font-size: 9px;
            color: #777;
            margin-top: 30px;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }

        .page-break {
            page-break-before: always;
        }

        .category-page {
            min-height: 80vh;
        }

        .generated-date {
            text-align: right;
            font-size: 9px;
            color: #999;
            margin-bottom: 6px;
        }

        .stats-info {
            text-align: center;
            font-size: 12px;
            color: #666;
            margin-bottom: 8px;
            background-color: #e8f4fd;
            padding: 8px;
            border-radius: 4px;
        }

        .density-high {
            background-color: #fff5f5 !important;
            font-weight: bold;
        }

        .density-medium {
            background-color: #fffbf0 !important;
        }

        .density-low {
            background-color: #f0fff4 !important;
        }

        .price-highlight {
            font-weight: bold;
            color: #E74C3C;
        }

        .category-header {
            background: linear-gradient(135deg, #E74C3C 0%, #c0392b 100%);
            color: white;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 6px;
            text-align: center;

            /* НОВОЕ: добавляем рамку */
            border: 2px solid #E74C3C;
            box-shadow: 0 2px 8px rgba(231, 76, 60, 0.3);
        }

        .category-header h2 {
            margin: 0;
            border: none;
            color: white;
            font-size: 14px;
        }

        /* Дополнительно для мобильных */
        @media (max-width: 768px) {
            h2 {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                color: #ffffff !important;
            }

            .category-header {
                border: 2px solid #E74C3C !important;
                background: linear-gradient(135deg, #E74C3C 0%, #c0392b 100%) !important;
                color: white !important;
                padding: 10px !important;
                border-radius: 5px !important;
                box-shadow: 0 2px 8px rgba(231, 76, 60, 0.4) !important;
            }

            h1 {
                font-size: 2rem !important;
            }

            h2 {
                font-size: 1.5rem !important;
            }

            table th,
            table td {
                font-size: 13px !important;
            }
        }
    </style>
</head>

<body>
    <!-- <div class="container">
        <div class="generated-date">
            Сформирован: {{ generation_date }}
        </div> -->

    <!-- Титульная страница -->
    <div class="header">
        <img src="/static/images/photo_2024-05-27_15-00-14.jpg" alt="China Together" class="logo">
        <h1>China Together</h1>
        <p class="subtitle">Актуальные тарифы доставки из Китая</p>

        <div class="stats-info">
            📊 Доступно {{ total_categories }} категорий товаров
        </div>
    </div>

    {% for category, rows in categories_data.items() %}
    {% if not loop.first %}
    <div class="page-break"></div>
    {% endif %}

    <div class="category-page">
        <div class="category-header">
            {% if category == 'Обычные товары' %}
            <h2>Обычный товар/Хоз товары/Сумки/Коврики/Шапки</h2>
            {% else %}
            <h2>{{ category }}</h2>
            {% endif %}
        </div>

        <table>
            <thead>
                <tr>
                    <th style="width: 40%;">Плотность (кг/м³)</th>
                    {% if category == 'Обувь' %}
                    <th style="width: 30%;">Доставка оригинала ($/kg)</th>
                    {% else %}
                    <th style="width: 30%;">Быстрое авто ($/kg)</th>
                    {% endif %}
                    {% if category == 'Обувь' %}
                    <th style="width: 30%;">Доставка реплики ($/kg)</th>
                    {% else %}
                    <th style="width: 30%;">Обычное авто ($/kg)</th>
                    {% endif %}
                </tr>
            </thead>
            <tbody>
                {% for row in rows %}
                <tr {% if row.fast_delivery_cost>= 3.5 %}class="density-medium"{% elif row.fast_delivery_cost >= 2.5
                    %}class="density-medium"{% else %}class="density-medium"{% endif %}>
                    <td style="text-align: left; font-weight: bold;">{{ row.density_range }}</td>
                    {% if row.density_range == '<100' %} <td>По запросу</td>
                        {% else %}
                        <td>${{ "%.2f"|format(row.fast_delivery_cost) }}</td>
                        {% endif %}
                        {% if row.density_range == '<100' %} <td>По запросу</td>
                            {% else %}
                            <td>${{ "%.2f"|format(row.regular_delivery_cost) }}</td>
                            {% endif %}
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="additional-info">
            <h3>📋 Важная информация по доставке:</h3>
            <ol>
                {% if category == 'Обувь' %}
                <li><strong>Сроки доставки:</strong> Быстрое авто (12-15 дней)</li>
                {% elif category == 'Обычные товары' %}
                <li><strong>Сроки доставки:</strong> Быстрое авто (13-16 дней), Обычное авто (17-25 дней)</li>
                {% else %}
                <li><strong>Сроки доставки:</strong> Быстрое авто (15-18 дней), Обычное авто (20-25 дней)</li>
                {% endif %}
                <li><strong>Страхование товара:</strong>
                    <ul style="margin: 2px 0; padding-left: 15px;">
                        <li>до 20$/kg — 1% от стоимости</li>
                        <li>20-30$/kg — 2% от стоимости</li>
                        <li>30-40$/kg — 3% от стоимости</li>
                        <li>свыше 40$/kg — обсуждается индивидуально</li>
                    </ul>
                </li>
                <li><strong>Стоимость упаковки:</strong>
                    <ul style="margin: 2px 0; padding-left: 15px;">
                        <li>Мешок + скотч: 3$/место</li>
                        <li>Уголки из картона + скотч: 8$/место</li>
                        <li>Деревянный каркас + скотч: 15$/место</li>
                        <li>Паллета: 30$/куб</li>
                    </ul>
                </li>
                <li><strong>Дополнительные условия:</strong> Копии брендов +0.2$ к тарифу</li>
                <li><strong>Запрещенные к перевозке товары:</strong> порошковые вещества, легковоспламеняющиеся
                    материалы, жидкости, табачные изделия, лекарственные препараты, режущие предметы, продукты питания
                </li>
            </ol>
        </div>

        {% if not loop.last %}
        <div style="margin-top: 2px; text-align: center; font-size: 8px; color: #999;">
            Страница {{ loop.index }} из {{ loop.length }}
        </div>
        {% endif %}
    </div>
    {% endfor %}

    <div class="footer">
        <p><strong>© {{ generation_date[:4] }} China Together</strong></p>
        <p>📞 Контакты: t.me/Togetherchina | 📧 @Chinatogether_bot</p>
        <p>🌐 Ваш надёжный партнёр по доставке из Китая</p>
    </div>
    </div>
</body>

</html>
