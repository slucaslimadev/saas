from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from datetime import datetime
import sqlite3
import re
import io
import csv
from contextlib import closing


app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui'
app.config['DATABASE_TIMEOUT'] = 30

# Configurações do banco de dados
def get_db_connection():
    conn = sqlite3.connect('database.db', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with closing(get_db_connection()) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS veiculos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_entrada TEXT NOT NULL,
                nome_carro TEXT NOT NULL,
                placa TEXT NOT NULL,
                valor REAL NOT NULL,
                tipo TEXT NOT NULL,
                forma_pagamento TEXT NOT NULL,
                observacao TEXT,
                pago BOOLEAN NOT NULL,
                data_saida TEXT,
                status TEXT NOT NULL,
                observacao_final TEXT,
                status_pagamento TEXT DEFAULT 'parcial'
            )
        ''')
        
        conn.commit()

def formatar_data(data_str, formato_origem=None, formato_saida=None):
    if not data_str:
        return ""
    
    # Formatos possíveis que podem vir do banco ou do formulário
    formatos_entrada = [
        '%Y-%m-%d %H:%M:%S',  # Formato do banco de dados
        '%Y-%m-%dT%H:%M',     # Formato do input datetime-local
        '%d/%m/%Y %H:%M'      # Formato exibido para o usuário
    ]
    
    # Se um formato específico foi fornecido, tente apenas com ele
    if formato_origem:
        formatos_entrada = [formato_origem]
    
    for fmt in formatos_entrada:
        try:
            data_obj = datetime.strptime(data_str, fmt)
            return data_obj.strftime(formato_saida if formato_saida else '%d/%m/%Y %H:%M')
        except ValueError:
            continue
    
    return data_str  # Retorna original se não conseguir converter

# Rotas
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        try:
            # Validação da data de entrada
            data_entrada_str = request.form['data_entrada']  # Formato: YYYY-MM-DDTHH:MM
            data_entrada = datetime.strptime(data_entrada_str, '%Y-%m-%dT%H:%M')
            data_atual = datetime.now()
            
            if data_entrada > data_atual:
                flash('A data de entrada não pode ser maior que a data atual', 'danger')
                return redirect(url_for('entrada'))
            
            placa = request.form['placa'].upper()
            if not re.match(r'^[A-Z]{3}\d{4}$', placa):
                flash('Formato de placa inválido! Use 3 letras e 4 números (Ex: ABC1234)', 'danger')
                return redirect(url_for('entrada'))

            with closing(get_db_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    status_pagamento = request.form['pago']
                    cursor.execute('''
                        INSERT INTO veiculos (
                            data_entrada, nome_carro, placa, valor, tipo,
                            forma_pagamento, observacao, pago, status, status_pagamento
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'EM SERVIÇO', ?)
                    ''', (
                        data_entrada.strftime('%Y-%m-%d %H:%M:%S'),
                        request.form['nome_carro'],
                        placa,
                        float(request.form['valor']),
                        request.form['tipo'],
                        request.form['forma_pagamento'],
                        request.form.get('observacao', ''),
                        status_pagamento == 'pago',
                        status_pagamento
                    ))
            
            flash('Veículo registrado com sucesso!', 'success')
            return redirect(url_for('relatorio'))
        
        except Exception as e:
            flash(f'Erro ao registrar veículo: {str(e)}', 'danger')
    
    return render_template('entrada.html')

@app.route('/saida/<int:veiculo_id>', methods=['GET', 'POST'])
def saida(veiculo_id):
    if request.method == 'POST':
        try:
            with closing(get_db_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE veiculos 
                        SET data_saida = ?, 
                            status = 'FINALIZADO',
                            observacao_final = ?
                        WHERE id = ?
                    ''', (
                        formatar_data(request.form['data_saida']),
                        request.form.get('observacao_final', ''),
                        veiculo_id
                    ))
            
            flash('Saída do veículo registrada com sucesso!', 'success')
            return redirect(url_for('relatorio'))
        
        except Exception as e:
            flash(f'Erro ao registrar saída: {str(e)}', 'danger')
    
    return render_template('saida.html', veiculo_id=veiculo_id)

@app.route('/editar/<int:veiculo_id>', methods=['GET', 'POST'])
def editar(veiculo_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                with conn:
                    status_pagamento = request.form['pago']
                    
                    # Converter a data de entrada para o formato do banco
                    data_entrada_str = request.form['data_entrada']
                    data_entrada = datetime.strptime(data_entrada_str, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Converter a data de saída (se existir)
                    data_saida = None
                    if request.form.get('data_saida'):
                        data_saida = datetime.strptime(request.form['data_saida'], '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')

                    cursor.execute('''
                        UPDATE veiculos SET
                            data_entrada = ?,
                            data_saida = ?,
                            nome_carro = ?,
                            placa = ?,
                            valor = ?,
                            tipo = ?,
                            forma_pagamento = ?,
                            observacao = ?,
                            pago = ?,
                            status = ?,
                            observacao_final = ?,
                            status_pagamento = ?
                        WHERE id = ?
                    ''', (
                        data_entrada,
                        data_saida,
                        request.form['nome_carro'],
                        request.form['placa'].upper(),
                        float(request.form['valor']),
                        request.form['tipo'],
                        request.form['forma_pagamento'],
                        request.form.get('observacao', ''),
                        status_pagamento == 'pago',
                        request.form['status'],
                        request.form.get('observacao_final', ''),
                        status_pagamento,
                        veiculo_id
                    ))
                    
                    flash('Veículo atualizado com sucesso!', 'success')
                    return redirect(url_for('historico'))
            
            except Exception as e:
                flash(f'Erro ao atualizar veículo: {str(e)}', 'danger')
        
        # Buscar o veículo para edição
        cursor.execute('SELECT * FROM veiculos WHERE id = ?', (veiculo_id,))
        veiculo = cursor.fetchone()
        
        if veiculo:
            veiculo = dict(veiculo)
            # Converter a data de entrada para o formato datetime-local
            if veiculo['data_entrada']:
                try:
                    dt_entrada = datetime.strptime(veiculo['data_entrada'], '%Y-%m-%d %H:%M:%S')
                    veiculo['data_entrada_template'] = dt_entrada.strftime('%Y-%m-%dT%H:%M')
                except ValueError:
                    veiculo['data_entrada_template'] = ''
            
            # Converter a data de saída para o formato datetime-local
            if veiculo['data_saida']:
                try:
                    dt_saida = datetime.strptime(veiculo['data_saida'], '%Y-%m-%d %H:%M:%S')
                    veiculo['data_saida_template'] = dt_saida.strftime('%Y-%m-%dT%H:%M')
                except ValueError:
                    veiculo['data_saida_template'] = ''
    
    if not veiculo:
        flash('Veículo não encontrado!', 'danger')
        return redirect(url_for('historico'))
    
    return render_template('editar.html', veiculo=veiculo)

@app.route('/relatorio')
def relatorio():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT *, 
                CASE 
                    WHEN status_pagamento = 'pago' THEN 'Pago'
                    WHEN status_pagamento = 'parcial' THEN 'Parcialmente Pago'
                    ELSE 'Não Pago'
                END as status_pagamento_texto
            FROM veiculos 
            WHERE status = "EM SERVIÇO" 
            ORDER BY data_entrada DESC
        ''')
        veiculos = cursor.fetchall()
    
    return render_template('relatorio.html', veiculos=veiculos)

@app.route('/historico')
def historico():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT *, 
                CASE 
                    WHEN status_pagamento = 'pago' THEN 'Pago'
                    WHEN status_pagamento = 'parcial' THEN 'Parcialmente Pago'
                    ELSE 'Não Pago'
                END as status_pagamento_texto
            FROM veiculos 
            ORDER BY data_entrada DESC
        ''')
        veiculos = cursor.fetchall()
    
    return render_template('historico.html', veiculos=veiculos)
@app.route('/exportar_historico')
def exportar_historico():
    # Criar um arquivo CSV em memória
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')  # Usando ponto-e-vírgula como delimitador
    
    # Escrever cabeçalho
    writer.writerow([
        'ID', 'Data Entrada', 'Data Saída', 'Veículo', 'Placa', 
        'Valor', 'Tipo', 'Forma Pagamento', 'Observação', 
        'Pago', 'Status', 'Observação Final', 'Status Pagamento'
    ])
    
    # Buscar todos os veículos
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM veiculos ORDER BY data_entrada DESC')
        veiculos = cursor.fetchall()
        
        # Escrever dados
        for veiculo in veiculos:
            writer.writerow([
                veiculo['id'],
                veiculo['data_entrada'],
                veiculo['data_saida'] if veiculo['data_saida'] else '',
                veiculo['nome_carro'],
                veiculo['placa'],
                f"R$ {veiculo['valor']:.2f}".replace('.', ','),  # Formato brasileiro
                veiculo['tipo'],
                veiculo['forma_pagamento'],
                veiculo['observacao'] if veiculo['observacao'] else '',
                'Sim' if veiculo['pago'] else 'Não',
                veiculo['status'],
                veiculo['observacao_final'] if veiculo['observacao_final'] else '',
                veiculo['status_pagamento']
            ])
    
    # Configurar resposta
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=historico_veiculos.csv'
    response.headers['Content-type'] = 'text/csv; charset=utf-8'
    
    return response

@app.route('/dashboard')
def dashboard():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        
        # 1. Estatísticas Básicas
        cursor.execute('SELECT COUNT(*) FROM veiculos WHERE status = "EM SERVIÇO"')
        em_servico = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM veiculos WHERE status = "FINALIZADO"')
        finalizados = cursor.fetchone()[0]
        
        # 2. Receita Total (CORRIGIDA)
        cursor.execute('''
            SELECT COALESCE(SUM(valor), 0) as total 
            FROM veiculos 
            WHERE status_pagamento = 'pago' 
            AND status = 'FINALIZADO'
        ''')
        receita = float(cursor.fetchone()['total'])

        dados_receita = cursor.fetchall()
        meses = [row['mes'] for row in dados_receita]
        valores_receita = [float(row['total']) for row in dados_receita]

        dados_tipos = cursor.fetchall()
        tipos_veiculos = [row['tipo'] for row in dados_tipos]
        quantidades_tipos = [row['quantidade'] for row in dados_tipos]

        # 4. Últimos Veículos
        cursor.execute('SELECT * FROM veiculos ORDER BY id DESC LIMIT 5')
        ultimos_veiculos = cursor.fetchall()



    return render_template('dashboard.html',
                         em_servico=em_servico,
                         finalizados=finalizados,
                         receita=receita,
                         veiculos=ultimos_veiculos,
                         meses=meses,
                         valores_receita=valores_receita,
                         tipos_veiculos=tipos_veiculos,
                         quantidades_tipos=quantidades_tipos)

@app.route('/excluir/<int:veiculo_id>')
def excluir(veiculo_id):
    try:
        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM veiculos WHERE id = ?', (veiculo_id,))
        
        flash('Registro excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir registro: {str(e)}', 'danger')
    return redirect(url_for('historico'))



# Inicialização
if __name__ == '__main__':
    init_db()
    app.run(debug=True)