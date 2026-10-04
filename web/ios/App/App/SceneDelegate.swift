import UIKit
import Capacitor

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }

        window = UIWindow(windowScene: windowScene)
        window?.rootViewController = CAPBridgeViewController()
        window?.makeKeyAndVisible()

        SceneDelegateProxy.shared.scene(scene, willConnectTo: session, options: connectionOptions)
        // Arranque en frío desde «Abrir con» / «Compartir» con un PDF
        entregarDocumentos(connectionOptions.urlContexts)
    }

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        let otros = entregarDocumentos(URLContexts)
        if !otros.isEmpty {
            SceneDelegateProxy.shared.scene(scene, openURLContexts: otros)
        }
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        SceneDelegateProxy.shared.scene(scene, continue: userActivity)
    }

    /// Los PDF que llegan de Archivos («Abrir con») pertenecen a otra app: se copian a una
    /// carpeta propia (con el permiso temporal de iOS) y se pasan a la parte web.
    @discardableResult
    private func entregarDocumentos(_ contextos: Set<UIOpenURLContext>) -> Set<UIOpenURLContext> {
        var otros = Set<UIOpenURLContext>()
        for contexto in contextos {
            let url = contexto.url
            guard url.isFileURL, let copia = copiarDocumento(url) else {
                otros.insert(contexto)
                continue
            }
            _ = ApplicationDelegateProxy.shared.application(UIApplication.shared, open: copia, options: [:])
        }
        return otros
    }

    private func copiarDocumento(_ url: URL) -> URL? {
        let acceso = url.startAccessingSecurityScopedResource()
        defer { if acceso { url.stopAccessingSecurityScopedResource() } }
        let carpeta = FileManager.default.temporaryDirectory.appendingPathComponent("Recibidos", isDirectory: true)
        try? FileManager.default.createDirectory(at: carpeta, withIntermediateDirectories: true)
        let destino = carpeta.appendingPathComponent(url.lastPathComponent)
        try? FileManager.default.removeItem(at: destino)
        var error: NSError?
        var resultado: URL?
        NSFileCoordinator().coordinate(readingItemAt: url, options: .withoutChanges, error: &error) { leible in
            if (try? FileManager.default.copyItem(at: leible, to: destino)) != nil {
                resultado = destino
            }
        }
        return resultado
    }
}
