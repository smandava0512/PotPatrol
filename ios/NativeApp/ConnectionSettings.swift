import Foundation
import PotPatrolCore
import Security

enum DeviceTokenStore {
    private static let service = "com.potpatrol.device-token"
    static func read() -> String {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: "device",
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return "" }
        return String(data: data, encoding: .utf8) ?? ""
    }
    static func save(_ token: String) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: "device"]
        let attributes: [String: Any] = [kSecValueData as String: Data(token.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            let result = SecItemAdd(query.merging(attributes) { _, value in value } as CFDictionary, nil)
            guard result == errSecSuccess else { throw PotPatrolAPIError.configuration("The device token could not be saved in Keychain.") }
        } else if status != errSecSuccess {
            throw PotPatrolAPIError.configuration("The device token could not be updated in Keychain.")
        }
    }
}

struct ConnectionSettings {
    var baseURL: String
    var developmentHTTP: Bool
    init() {
        baseURL = UserDefaults.standard.string(forKey: "PotPatrol.serverURL") ?? ""
        developmentHTTP = UserDefaults.standard.bool(forKey: "PotPatrol.developmentHTTP")
    }
    func save() {
        UserDefaults.standard.set(baseURL, forKey: "PotPatrol.serverURL")
        UserDefaults.standard.set(developmentHTTP, forKey: "PotPatrol.developmentHTTP")
    }
    func client() throws -> PotPatrolAPIClient {
        guard let url = URL(string: baseURL.trimmingCharacters(in: .whitespacesAndNewlines)), !baseURL.isEmpty else {
            throw PotPatrolAPIError.configuration("Connect to your analysis server in Settings. The drive stays saved on this iPhone.")
        }
        var allowHTTP = false
        #if DEBUG
        allowHTTP = developmentHTTP
        #endif
        return PotPatrolAPIClient(connection: try APIConnection(baseURL: url, deviceToken: DeviceTokenStore.read(), allowDevelopmentHTTP: allowHTTP))
    }
}
