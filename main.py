import flet as ft
import random
import time
import threading

class LutaMMA:
    def __init__(self, lutador_a, lutador_b):
        self.lutador_a = lutador_a
        self.lutador_b = lutador_b
        self.rounds = []  
        self.finalizada = False

class TorneioApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.lutas = []
        self.luta_atual = None
        
        self.tempo_restante = 300  
        self.timer_rodando = False
        self.thread_timer = None
        
        self.page.title = "MMA Torneio Organizer"
        self.page.theme_mode = ft.ThemeMode.DARK
        
        self.txt_lutador_a = ft.TextField(label="Lutador A", expand=True)
        self.txt_lutador_b = ft.TextField(label="Lutador B", expand=True)
        self.lv_lutas = ft.ListView(expand=True, spacing=10)
        
        self.lbl_timer = ft.Text("05:00", size=60, weight=ft.FontWeight.BOLD)
        self.btn_timer = ft.ElevatedButton("Iniciar", on_click=self.toggle_timer, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
        
        self.lbl_luta_ativa = ft.Text("Nenhuma luta selecionada", size=18, weight=ft.FontWeight.BOLD)
        self.lbl_round_atual = ft.Text("Round 1", size=16)
        self.txt_pts_a = ft.TextField(value="10", label="Pts A", width=80, text_align=ft.TextAlign.CENTER)
        self.txt_pts_b = ft.TextField(value="9", label="Pts B", width=80, text_align=ft.TextAlign.CENTER)
        self.lv_historico_rounds = ft.ListView(expand=True, spacing=5)
        self.lbl_total_luta = ft.Text("Total: 0 x 0", size=20, weight=ft.FontWeight.BOLD)

        self.construir_interface()

    def construir_interface(self):
        aba_chaveamento = ft.Container(
            padding=20,
            content=ft.Column([
                ft.Text("Definir Lutas", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([self.txt_lutador_a, ft.Text("VS"), self.txt_lutador_b]),
                ft.ElevatedButton("Adicionar Luta", on_click=self.adicionar_luta, icon=ft.Icons.ADD),
                ft.Divider(),
                ft.ElevatedButton("Sortear Ordem", on_click=self.sortear_ordem, icon=ft.Icons.SHUFFLE, bgcolor=ft.Colors.BLUE_900),
                ft.Text("Próximos Confrontos:", size=16, weight=ft.FontWeight.BOLD),
                self.lv_lutas
            ], spacing=15)
        )

        aba_combate = ft.Container(
            padding=20,
            content=ft.Column([
                self.lbl_luta_ativa,
                ft.Divider(),
                ft.Column([
                    ft.Row([
                        ft.TextButton("1 Min", on_click=lambda _: self.definir_tempo(60)),
                        ft.TextButton("3 Min", on_click=lambda _: self.definir_tempo(180)),
                        ft.TextButton("5 Min", on_click=lambda _: self.definir_tempo(300)),
                    ], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([self.lbl_timer], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([
                        self.btn_timer,
                        ft.ElevatedButton("Resetar", on_click=self.resetar_timer, bgcolor=ft.Colors.RED_900),
                    ], alignment=ft.MainAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER),
                ft.Divider(),
                ft.Text("Pontuação do Round", size=16, weight=ft.FontWeight.BOLD),
                self.lbl_round_atual,
                ft.Row([
                    ft.Column([ft.Text("Lutador A"), self.txt_pts_a], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("vs", size=20),
                    ft.Column([ft.Text("Lutador B"), self.txt_pts_b], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=30),
                ft.Row([
                    ft.ElevatedButton("Salvar Round", on_click=self.salvar_round, icon=ft.Icons.SAVE, bgcolor=ft.Colors.GREEN_700),
                ], alignment=ft.MainAxisAlignment.CENTER),
                ft.Divider(),
                self.lbl_total_luta,
                self.lv_historico_rounds
            ], spacing=10, scroll=ft.ScrollMode.AUTO)
        )

        tabs = ft.Tabs(
            selected_index=0,
            tabs=[
                ft.Tab(text="Chaveamento", icon=ft.Icons.FORMAT_LIST_BULLETED, content=aba_chaveamento),
                ft.Tab(text="Combate & Placar", icon=ft.Icons.TIMER, content=aba_combate),
            ],
            expand=1
        )
        self.page.add(tabs)

    def adicionar_luta(self, e):
        if self.txt_lutador_a.value and self.txt_lutador_b.value:
            nova_luta = LutaMMA(self.txt_lutador_a.value, self.txt_lutador_b.value)
            self.lutas.append(nova_luta)
            self.txt_lutador_a.value = ""
            self.txt_lutador_b.value = ""
            self.atualizar_lista_lutas()
            self.page.update()

    def sortear_ordem(self, e):
        if self.lutas:
            random.shuffle(self.lutas)
            self.atualizar_lista_lutas()
            self.page.update()

    def atualizar_lista_lutas(self):
        self.lv_lutas.controls.clear()
        for idx, luta in enumerate(self.lutas):
            status = " (Encerrada)" if luta.finalizada else ""
            self.lv_lutas.controls.append(
                ft.Card(
                    content=ft.ListTile(
                        title=ft.Text(f"{luta.lutador_a} VS {luta.lutador_b}{status}"),
                        subtitle=ft.Text(f"Posição: {idx + 1}"),
                        trailing=ft.IconButton(ft.Icons.PLAY_ARROW, on_click=lambda _, l=luta: self.selecionar_luta(l)),
                    )
                )
            )

    def selecionar_luta(self, luta):
        self.luta_atual = luta
        self.lbl_luta_ativa.value = f"LUTA: {luta.lutador_a} VS {luta.lutador_b}"
        self.atualizar_painel_pontos()
        self.page.update()

    def definir_tempo(self, segundos):
        if not self.timer_rodando:
            self.tempo_restante = segundos
            self.atualizar_texto_timer()
            self.page.update()

    def atualizar_texto_timer(self):
        mins, segs = divmod(self.tempo_restante, 60)
        self.lbl_timer.value = f"{mins:02d}:{segs:02d}"

    def toggle_timer(self, e):
        if self.timer_rodando:
            self.timer_rodando = False
            self.btn_timer.text = "Iniciar"
            self.btn_timer.bgcolor = ft.Colors.GREEN
        else:
            self.timer_rodando = True
            self.btn_timer.text = "Pausar"
            self.btn_timer.bgcolor = ft.Colors.ORANGE_800
            self.thread_timer = threading.Thread(target=self.rodar_timer, daemon=True)
            self.thread_timer.start()
        self.page.update()

    def resetar_timer(self, e):
        self.timer_rodando = False
        self.tempo_restante = 300
        self.btn_timer.text = "Iniciar"
        self.btn_timer.bgcolor = ft.Colors.GREEN
        self.lbl_timer.color = ft.Colors.WHITE
        self.atualizar_texto_timer()
        self.page.update()

    def rodar_timer(self):
        if self.tempo_restante > 0 and self.timer_rodando:
            # Alerta sonoro de início do round
            self.page.window_bell() 
            
        while self.tempo_restante > 0 and self.timer_rodando:
            time.sleep(1)
            self.tempo_restante -= 1
            self.atualizar_texto_timer()
            
            # Faltando 10 segundos: muda para vermelho e emite bipes rápidos
            if self.tempo_restante <= 10 and self.tempo_restante > 0:
                self.lbl_timer.color = ft.Colors.RED
                self.page.window_bell()
            
            self.page.update()
            
        if self.tempo_restante == 0:
            self.timer_rodando = False
            self.btn_timer.text = "Iniciar"
            self.btn_timer.bgcolor = ft.Colors.GREEN
            self.lbl_timer.color = ft.Colors.WHITE
            # Fim do Round: toca 3 alertas seguidos
            for _ in range(3):
                self.page.window_bell()
                time.sleep(0.3)
            self.page.update()

    def salvar_round(self, e):
        if not self.luta_atual:
            return
        try:
            pts_a = int(self.txt_pts_a.value)
            pts_b = int(self.txt_pts_b.value)
        except ValueError:
            return

        self.luta_atual.rounds.append((pts_a, pts_b))
        self.txt_pts_a.value = "10"
        self.txt_pts_b.value = "9"
        self.atualizar_painel_pontos()
        self.page.update()

    def atualizar_painel_pontos(self):
        if not self.luta_atual:
            return
        
        self.lbl_round_atual.value = f"Round {len(self.luta_atual.rounds) + 1}"
        self.lv_historico_rounds.controls.clear()
        
        total_a, total_b = 0, 0
        for r_idx, (p_a, p_b) in enumerate(self.luta_atual.rounds):
            total_a += p_a
            total_b += p_b
            self.lv_historico_rounds.controls.append(
                ft.Text(f"Round {r_idx + 1}: {p_a} x {p_b}", size=14, color=ft.Colors.GREY_400)
            )
            
        self.lbl_total_luta.value = f"Total Acumulado: {total_a} x {total_b}"

def main(page: ft.Page):
    TorneioApp(page)

ft.app(target=main)
